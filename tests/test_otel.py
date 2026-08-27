"""Tests de instrumentación OTEL opcional en Worker._execute.

`_tracer` se resuelve una sola vez al importar `django_task_psql.worker` (según
si `opentelemetry-api` está instalado). Estos tests monkeypatchean ese
atributo de módulo directamente para simular "tracer configurado" y "sin
opentelemetry" sin depender de reordenar imports.
"""

import pytest
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from django_task_psql import worker as worker_module
from django_task_psql.models import TaskRow, TaskStatus

from . import tasks
from .conftest import make_worker

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def span_exporter(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(worker_module, "_tracer", provider.get_tracer(__name__))
    return exporter


def test_execute_exitoso_emite_span_con_atributos(span_exporter):
    TaskRow.objects.create(task_path=tasks.ok_task.module_path, args=[7], queue_name="test-ok")
    w = make_worker("test-ok")
    w._iterate()
    w.wait_inflight()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == f"django_task_psql.{tasks.ok_task.module_path}"
    assert span.attributes["django_task_psql.attempt"] == 1
    assert span.attributes["django_task_psql.queue_name"] == "test-ok"
    assert span.status.status_code == otel_trace.StatusCode.UNSET


def test_execute_fallido_marca_span_como_error(span_exporter):
    TaskRow.objects.create(task_path=tasks.always_fails.module_path, queue_name="test-fail", max_attempts=1)
    w = make_worker("test-fail")
    w._iterate()
    w.wait_inflight()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.status.status_code == otel_trace.StatusCode.ERROR
    assert [e.name for e in span.events] == ["exception"]


def test_sin_tracer_configurado_no_rompe(monkeypatch):
    """Simula `opentelemetry-api` no instalado (`_tracer is None`) — el
    worker debe seguir funcionando idéntico a antes de la instrumentación."""
    monkeypatch.setattr(worker_module, "_tracer", None)
    TaskRow.objects.create(task_path=tasks.ok_task.module_path, args=[3], queue_name="test-ok")
    w = make_worker("test-ok")
    w._iterate()
    w.wait_inflight()
    row = TaskRow.objects.first()
    assert row.status == TaskStatus.SUCCESSFUL
    assert row.return_value == 6
