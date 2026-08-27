"""Config del worker vía variables de entorno ``TASK_WORKER_*``.

Todo lo que el worker necesita para correr en producción sin flags CLI ni
tocar código. Un flag CLI explícito (``--concurrency``, ``--queues``) siempre
gana sobre el env var correspondiente.
"""

import os


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _str(name: str, default: str) -> str:
    return os.environ.get(name, default)


TASK_WORKER_CONCURRENCY = _int("TASK_WORKER_CONCURRENCY", 1)
TASK_WORKER_STALE_MINUTES = _int("TASK_WORKER_STALE_MINUTES", 5)
TASK_WORKER_BACKOFF_BASE_S = _int("TASK_WORKER_BACKOFF_BASE_S", 30)
TASK_WORKER_HEARTBEAT_S = _int("TASK_WORKER_HEARTBEAT_S", 5)
TASK_WORKER_DB_ALIAS = _str("TASK_WORKER_DB_ALIAS", "default")
TASK_WORKER_SPAN_PREFIX = _str("TASK_WORKER_SPAN_PREFIX", "django_task_psql")
