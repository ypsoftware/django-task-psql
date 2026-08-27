import pytest
from django.tasks import task_backends
from django.tasks.base import TaskResultStatus

from django_task_psql.models import TaskRow

from . import tasks

pytestmark = pytest.mark.django_db


def test_enqueue_crea_fila_y_devuelve_task_result():
    result = tasks.ok_task.enqueue(3)
    row = TaskRow.objects.get(id=result.id)
    assert row.task_path == tasks.ok_task.module_path
    assert row.args == [3]
    assert result.status == TaskResultStatus.READY
    assert result.backend == "default"


def test_get_result_devuelve_lo_mismo_que_enqueue():
    result = tasks.ok_task.enqueue(3)
    fetched = task_backends["default"].get_result(result.id)
    assert fetched.id == result.id
    assert fetched.args == [3]
    assert fetched.status == TaskResultStatus.READY


def test_get_result_inexistente_lanza():
    from django.tasks.exceptions import TaskResultDoesNotExist

    with pytest.raises(TaskResultDoesNotExist):
        task_backends["default"].get_result("00000000-0000-0000-0000-000000000000")


def test_priority_afecta_orden_de_claim():
    from .conftest import make_worker

    low = tasks.ok_task.using(priority=-5).enqueue(1)
    high = tasks.ok_task.using(priority=5).enqueue(2)

    w = make_worker("test-ok")
    first = w._claim()
    assert str(first["id"]) == high.id
    second = w._claim()
    assert str(second["id"]) == low.id


def test_run_after_defiere_la_tarea():
    from datetime import timedelta

    from django.utils import timezone

    result = tasks.ok_task.using(run_after=timezone.now() + timedelta(minutes=5)).enqueue(1)
    row = TaskRow.objects.get(id=result.id)
    assert row.run_after > timezone.now()


def test_max_attempts_por_tarea_se_escribe_en_la_fila():
    result = tasks.task_max_attempts_5.enqueue(1)
    row = TaskRow.objects.get(id=result.id)
    assert row.max_attempts == 5


def test_max_attempts_sin_override_cae_al_default_del_backend():
    result = tasks.ok_task.enqueue(1)
    row = TaskRow.objects.get(id=result.id)
    assert row.max_attempts == 1
