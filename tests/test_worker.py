"""Tests del worker — claim + ejecución + reintentos + concurrencia.

Probamos _claim y _execute en aislamiento sin levantar el loop completo. El
loop con LISTEN/NOTIFY se valida manual contra un Postgres real.
"""

import threading
from datetime import timedelta

import pytest
from django.utils import timezone

from django_task_psql.models import TaskRow, TaskStatus

from . import tasks
from .conftest import make_worker

pytestmark = pytest.mark.django_db(transaction=True)
"""Necesitamos commits reales: ``FOR UPDATE SKIP LOCKED`` salta filas que
fueron insertadas en la transacción del test si pytest-django envuelve todo en
una sola ``atomic`` (default)."""


def test_claim_obtiene_ready_y_la_marca_running():
    TaskRow.objects.create(task_path=tasks.ok_task.module_path, args=[3], queue_name="test-ok")
    w = make_worker("test-ok")
    claimed = w._claim()
    assert claimed is not None
    assert claimed["task_path"] == tasks.ok_task.module_path
    row = TaskRow.objects.get(id=claimed["id"])
    assert row.status == TaskStatus.RUNNING
    assert row.attempt == 1


def test_claim_agrega_worker_id_a_worker_ids():
    TaskRow.objects.create(task_path=tasks.ok_task.module_path, args=[3], queue_name="test-ok")
    w = make_worker("test-ok")
    claimed = w._claim()
    row = TaskRow.objects.get(id=claimed["id"])
    assert row.worker_ids == [w.worker_id]


def test_claim_ignora_otras_colas():
    TaskRow.objects.create(task_path=tasks.ok_task.module_path, args=[1], queue_name="otra")
    w = make_worker("test-ok")
    assert w._claim() is None


def test_claim_ignora_no_vencidas():
    TaskRow.objects.create(
        task_path=tasks.ok_task.module_path, args=[1], queue_name="test-ok",
        run_after=timezone.now() + timedelta(minutes=5),
    )
    w = make_worker("test-ok")
    assert w._claim() is None


def test_execute_completa_y_guarda_resultado():
    TaskRow.objects.create(task_path=tasks.ok_task.module_path, args=[7], queue_name="test-ok")
    w = make_worker("test-ok")
    w._iterate()
    w.wait_inflight()
    row = TaskRow.objects.first()
    assert row.status == TaskStatus.SUCCESSFUL
    assert row.return_value == 14
    assert row.finished_at is not None


def test_execute_async_task():
    TaskRow.objects.create(task_path=tasks.async_task.module_path, args=[7], queue_name="test-ok")
    w = make_worker("test-ok")
    w._iterate()
    w.wait_inflight()
    row = TaskRow.objects.first()
    assert row.status == TaskStatus.SUCCESSFUL
    assert row.return_value == 8


def test_execute_task_no_registrada_falla():
    TaskRow.objects.create(task_path="modulo.fantasma", queue_name="test-ok", max_attempts=1)
    w = make_worker("test-ok")
    w._iterate()
    w.wait_inflight()
    row = TaskRow.objects.first()
    assert row.status == TaskStatus.FAILED
    assert "no registrada" in row.traceback


def test_execute_excepcion_reintenta_con_backoff():
    TaskRow.objects.create(task_path=tasks.always_fails.module_path, queue_name="test-fail", max_attempts=2)
    w = make_worker("test-fail")
    w._iterate()
    w.wait_inflight()
    row = TaskRow.objects.first()
    assert row.status == TaskStatus.READY
    assert row.attempt == 1
    assert "boom" in row.traceback
    assert row.run_after > timezone.now()


def test_worker_ids_se_acumula_entre_reintentos():
    t = TaskRow.objects.create(task_path=tasks.always_fails.module_path, queue_name="test-fail", max_attempts=2)
    w = make_worker("test-fail")
    w._iterate()
    w.wait_inflight()
    t.refresh_from_db()
    assert t.worker_ids == [w.worker_id]

    # Forzar el retry vencido para el segundo intento.
    TaskRow.objects.filter(id=t.id).update(run_after=timezone.now())
    w._iterate()
    w.wait_inflight()
    t.refresh_from_db()
    assert t.worker_ids == [w.worker_id, w.worker_id]


def test_execute_se_da_por_vencido_tras_max_attempts():
    t = TaskRow.objects.create(
        task_path=tasks.always_fails.module_path, queue_name="test-fail", max_attempts=2, attempt=1
    )
    TaskRow.objects.filter(id=t.id).update(run_after=timezone.now())
    w = make_worker("test-fail")
    w._iterate()
    w.wait_inflight()
    row = TaskRow.objects.first()
    assert row.status == TaskStatus.FAILED
    assert row.attempt == 2


def test_resultado_no_serializable_se_guarda_como_none():
    TaskRow.objects.create(task_path=tasks.not_serializable.module_path, queue_name="test-ok")
    w = make_worker("test-ok")
    w._iterate()
    w.wait_inflight()
    row = TaskRow.objects.first()
    assert row.status == TaskStatus.SUCCESSFUL
    assert row.return_value is None


def test_concurrencia_permite_tareas_en_paralelo():
    """Razón de ser de concurrency>1: una tarea lenta no debe bloquear que
    otra arranque. Con concurrency=1 la segunda `_iterate()` se quedaría
    esperando el semáforo hasta que la primera termine."""
    tasks.slow_started.clear()
    tasks.slow_continue.clear()
    ahora = timezone.now()
    TaskRow.objects.create(
        task_path=tasks.slow_task.module_path, queue_name="test-concurrency", run_after=ahora - timedelta(seconds=2)
    )
    TaskRow.objects.create(
        task_path=tasks.ok_task.module_path, args=[5], queue_name="test-concurrency",
        run_after=ahora - timedelta(seconds=1),
    )
    w = make_worker("test-concurrency", concurrency=2)

    assert w._iterate() is True
    assert tasks.slow_started.wait(timeout=2), "la tarea lenta nunca arrancó"

    result = {}

    def _try_second():
        from django.db import connections

        try:
            result["ok"] = w._iterate()
        finally:
            connections[w.db_alias].close()

    t = threading.Thread(target=_try_second, daemon=True)
    t.start()
    t.join(timeout=2)
    assert not t.is_alive(), "_iterate() se bloqueó esperando slot — concurrencia no está funcionando"
    assert result.get("ok") is True

    tasks.slow_continue.set()
    w.wait_inflight()

    slow_row = TaskRow.objects.get(task_path=tasks.slow_task.module_path)
    ok_row = TaskRow.objects.get(task_path=tasks.ok_task.module_path, queue_name="test-concurrency")
    assert slow_row.status == TaskStatus.SUCCESSFUL
    assert ok_row.status == TaskStatus.SUCCESSFUL


def test_run_and_release_no_traga_excepcion_fuera_del_try_interno(monkeypatch):
    """``_run_and_release`` corre dentro de un Future que ``_iterate`` no lee
    — sin su propio try/except, una excepción que escape de ``_execute`` (ej.
    el UPDATE a SUCCESSFUL falla transitoriamente) quedaría atrapada en el
    Future para siempre."""
    row = TaskRow.objects.create(task_path=tasks.ok_task.module_path, args=[1], queue_name="test-ok")
    w = make_worker("test-ok")

    def _blow_up(_row):
        raise RuntimeError("DB caida transitoriamente")

    monkeypatch.setattr(w, "_execute", _blow_up)
    w._run_and_release(
        {
            "id": row.id,
            "task_path": tasks.ok_task.module_path,
            "args": [1],
            "kwargs": {},
            "attempt": 1,
            "max_attempts": 3,
        }
    )

    row.refresh_from_db()
    assert row.status == TaskStatus.READY
    assert "excepcion no manejada" in row.traceback
    assert row.run_after > timezone.now()


def test_skip_locked_no_bloquea_otras_filas():
    TaskRow.objects.create(task_path=tasks.ok_task.module_path, args=[1], queue_name="test-ok")
    TaskRow.objects.create(task_path=tasks.ok_task.module_path, args=[2], queue_name="test-ok")
    w = make_worker("test-ok")
    a = w._claim()
    b = w._claim()
    c = w._claim()
    assert a is not None
    assert b is not None
    assert a["id"] != b["id"]
    assert c is None
