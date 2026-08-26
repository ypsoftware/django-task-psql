import pytest

from django_task_psql.worker import Worker

# Importar para que los @task se registren (equivalente a lo que hace
# load_registered_tasks() al arrancar el worker real).
from . import tasks  # noqa: F401

_workers_created: list[Worker] = []


def make_worker(queue: str, **kwargs) -> Worker:
    w = Worker(queues=[queue], **kwargs)
    _workers_created.append(w)
    return w


@pytest.fixture(autouse=True)
def _shutdown_workers():
    """Cierra el ThreadPoolExecutor de cada Worker creado en el test — si no,
    los threads quedan con su conexión a Postgres abierta y el teardown de la
    DB de test falla."""
    yield
    while _workers_created:
        _workers_created.pop()._executor.shutdown(wait=True)
