"""Loop del worker — SKIP LOCKED + LISTEN/NOTIFY + concurrencia real.

Diseño:

- El thread principal claimea UNA tarea a la vez vía ``UPDATE ... WHERE id =
  (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING ...`` y la somete a un
  ``ThreadPoolExecutor`` de ``concurrency`` threads — así varias tareas
  I/O-bound se solapan en vez de bloquear el proceso una por una. Un
  ``Semaphore(concurrency)`` limita cuántas tareas hay en vuelo: el thread
  principal no claimea una nueva hasta que haya un slot libre.
- Si claim falla (no hay pendientes), bloquea en ``LISTEN`` con fallback
  timeout (cubre delays vencidos sin NOTIFY).
- Ejecución sync dentro de cada thread (``Task.call()`` ya usa
  ``async_to_sync`` internamente para coroutines — no hace falta un loop de
  asyncio acá). Excepción → estado ``READY`` con ``run_after`` futuro
  (backoff exponencial) o ``FAILED`` si superó ``max_attempts``.
- Cada thread cierra su conexión al terminar una tarea (``connections[alias].close()``)
  — con el pool nativo de psycopg activo, eso devuelve la conexión al pool en
  vez de cortar el socket. Sin esto, un ThreadPoolExecutor de larga vida deja
  una conexión permanentemente agarrada por cada thread que alguna vez corrió
  una tarea — la causa raíz de fugas de pool en background workers.

Multi-proceso: SKIP LOCKED también deja correr N procesos worker en paralelo
sin cambios de código — combinable con la concurrencia intra-proceso.
"""

import json
import logging
import select
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta

from django.db import connections
from django.utils import timezone
from django.utils.crypto import get_random_string

try:
    from opentelemetry import trace
except ImportError:
    trace = None

from . import conf
from .backend import REGISTRY
from .loader import load_registered_tasks
from .models import TaskRow, TaskStatus

logger = logging.getLogger("django_task_psql")

NOTIFY_CHANNEL = "task_psql_new"

# None si el paquete opentelemetry-api no está instalado — get_tracer() con un
# TracerProvider no configurado por el host ya usa el no-op provider de la API
# OTEL, así que ni siquiera hace falta ese chequeo acá.
_tracer = trace.get_tracer(__name__) if trace is not None else None


@contextmanager
def _start_span(name: str, row: dict):
    """Span opcional alrededor de la ejecución de una tarea.

    Sin ``opentelemetry-api`` instalado (``trace is None``) o sin tracer
    configurado, no-opea: yield ``None`` y el caller salta el resto de la
    instrumentación (``record_exception``/``set_status``)."""
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        span.set_attribute("django_task_psql.attempt", row["attempt"])
        span.set_attribute("django_task_psql.queue_name", row["queue_name"])
        yield span


# CLAIM_SQL y RECOVER_STALE_SQL comparan contra un timestamp calculado en
# Python (pasado como parámetro), no contra el ``NOW()`` de Postgres: el reloj
# del proceso Python y el del servidor Postgres no están garantizados a
# coincidir a precisión de microsegundos (drift/jitter entre procesos, aunque
# compartan host). ``run_after`` se escribe siempre con ``timezone.now()`` de
# Python (default del modelo y backoff del worker) — comparar contra ``NOW()``
# de Postgres podía fallar el claim de forma intermitente cuando ambos
# relojes diferían por un puñado de microsegundos.
CLAIM_SQL = """
UPDATE task_psql_task
SET status = 'RUNNING', started_at = %s, attempt = attempt + 1,
    worker_ids = worker_ids || %s::jsonb
WHERE id = (
    SELECT id FROM task_psql_task
    WHERE status = 'READY'
      AND run_after <= %s
      AND queue_name = ANY(%s)
      AND backend_name = %s
    ORDER BY priority DESC, run_after
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id, task_path, args, kwargs, attempt, max_attempts, queue_name;
"""

RECOVER_STALE_SQL = """
UPDATE task_psql_task
SET status = 'READY'
WHERE status = 'RUNNING'
  AND started_at < %s
  AND queue_name = ANY(%s)
  AND backend_name = %s
RETURNING id;
"""


class Worker:
    def __init__(
        self,
        queues: list[str],
        *,
        concurrency: int | None = None,
        backend_alias: str = "default",
        db_alias: str | None = None,
        stale_minutes: int | None = None,
        backoff_base_s: int | None = None,
        heartbeat_s: int | None = None,
        batch: bool = False,
        max_tasks: int | None = None,
    ):
        self.queues = queues
        self.backend_alias = backend_alias
        self.db_alias = db_alias or conf.TASK_WORKER_DB_ALIAS
        self.concurrency = concurrency or conf.TASK_WORKER_CONCURRENCY
        self.stale_minutes = stale_minutes if stale_minutes is not None else conf.TASK_WORKER_STALE_MINUTES
        self.backoff_base_s = backoff_base_s or conf.TASK_WORKER_BACKOFF_BASE_S
        self.heartbeat_s = heartbeat_s or conf.TASK_WORKER_HEARTBEAT_S
        self.batch = batch
        self.max_tasks = max_tasks
        self.worker_id = get_random_string(32)

        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=self.concurrency, thread_name_prefix="task_psql")
        self._slots = threading.Semaphore(self.concurrency)
        self._completed_count = 0
        self._count_lock = threading.Lock()

    @property
    def _connection(self):
        return connections[self.db_alias]

    def stop(self, *args):
        logger.info("worker stop")
        self._running = False

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        load_registered_tasks()
        logger.info(
            "worker ready queues=%s tasks=%s concurrency=%s",
            self.queues,
            list(REGISTRY),
            self.concurrency,
        )
        self._recover_stale()
        with self._connection.cursor() as cur:
            cur.execute(f"LISTEN {NOTIFY_CHANNEL};")
        while self._running:
            claimed = self._iterate()
            if self.max_tasks is not None and self._completed_count >= self.max_tasks:
                logger.info("máximo de tareas (%d) alcanzado, saliendo", self.max_tasks)
                break
            if not claimed:
                if self.batch:
                    logger.info("batch: no hay más tareas pendientes, saliendo")
                    break
                self._wait_for_notify()
        logger.info("worker apagando, esperando tareas en curso")
        self._executor.shutdown(wait=True)

    def _recover_stale(self) -> None:
        """Tareas marcadas RUNNING por más de ``stale_minutes`` vuelven a READY.
        Cubre worker SIGKILL/OOM/crash que dejó fila huérfana."""
        cutoff = timezone.now() - timedelta(minutes=self.stale_minutes)
        with self._connection.cursor() as cur:
            cur.execute(RECOVER_STALE_SQL, [cutoff, list(self.queues), self.backend_alias])
            rows = cur.fetchall()
        if rows:
            logger.warning("recuperadas %s tareas stale ids=%s", len(rows), [r[0] for r in rows])

    def _iterate(self) -> bool:
        """Bloquea hasta que haya un slot libre, después claimea. Con
        concurrency=1 se comporta igual que un loop claim-ejecuta-repite."""
        self._slots.acquire()
        row = self._claim()
        if row is None:
            self._slots.release()
            return False
        self._executor.submit(self._run_and_release, row)
        return True

    def _run_and_release(self, row: dict) -> None:
        """``_execute`` ya atrapa las excepciones de la tarea del usuario, pero
        sus propios ``TaskRow.objects...update()`` (marcar completada,
        reintentar, fallar) quedan fuera de ese try. Si uno de esos updates
        revienta (ej. DB caída transitoriamente), la excepción sube hasta acá
        — y como esto corre dentro de un ``Future`` de ``ThreadPoolExecutor``
        que nadie lee (``_iterate`` no guarda el Future), sin este segundo
        try/except quedaría atrapada en silencio: la tarea se queda en
        RUNNING hasta el stale recovery en vez de fallar fuerte y quedar
        logueada.
        """
        try:
            self._execute(row)
        except Exception:
            logger.exception(
                "excepcion no manejada en _execute (fuera del try de la tarea) id=%s task_path=%s",
                row["id"],
                row["task_path"],
            )
            try:
                TaskRow.objects.using(self.db_alias).filter(id=row["id"]).update(
                    status=TaskStatus.READY,
                    run_after=timezone.now() + timedelta(seconds=self.backoff_base_s),
                    exception_class_path="",
                    traceback="worker: excepcion no manejada, ver logs",
                )
            except Exception:
                logger.exception(
                    "no se pudo re-marcar tarea tras excepcion no manejada id=%s — queda para stale recovery",
                    row["id"],
                )
        finally:
            with self._count_lock:
                self._completed_count += 1
            self._slots.release()
            # Con OPTIONS.pool activo, close() devuelve la conexión al pool de
            # psycopg (barato) en vez de cortar el socket — sin esto, la
            # conexión que este thread abrió queda viva hasta que el proceso
            # termina, aunque el thread ya haya sido joineado.
            self._connection.close()

    def wait_inflight(self) -> None:
        """Bloquea hasta que no haya tareas en ejecución. Para tests."""
        for _ in range(self.concurrency):
            self._slots.acquire()
        for _ in range(self.concurrency):
            self._slots.release()

    def _claim(self) -> dict | None:
        now = timezone.now()
        with self._connection.cursor() as cur:
            cur.execute(
                CLAIM_SQL,
                [now, json.dumps([self.worker_id]), now, list(self.queues), self.backend_alias],
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "task_path": row[1],
            "args": _coerce_json(row[2], default=[]),
            "kwargs": _coerce_json(row[3], default={}),
            "attempt": row[4],
            "max_attempts": row[5],
            "queue_name": row[6],
        }

    def _execute(self, row: dict) -> None:
        task = REGISTRY.get(row["task_path"])
        if task is None:
            self._fail(row, f"task {row['task_path']!r} no registrada")
            return
        span_name = f"{conf.TASK_WORKER_SPAN_PREFIX}.{row['task_path']}"
        with _start_span(span_name, row) as span:
            try:
                return_value = task.call(*row["args"], **row["kwargs"])
            except Exception as e:
                logger.exception("tarea fallo id=%s task_path=%s", row["id"], row["task_path"])
                if span is not None:
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                self._retry_or_fail(row, e)
                return
        TaskRow.objects.using(self.db_alias).filter(id=row["id"]).update(
            status=TaskStatus.SUCCESSFUL,
            return_value=return_value if _is_json_serializable(return_value) else None,
            finished_at=timezone.now(),
        )
        logger.info("tarea ok id=%s task_path=%s", row["id"], row["task_path"])

    def _retry_or_fail(self, row: dict, exc: Exception) -> None:
        if row["attempt"] >= row["max_attempts"]:
            self._fail(row, str(exc)[:5000], exception_class_path=f"{type(exc).__module__}.{type(exc).__qualname__}")
            return
        delay = self.backoff_base_s * (2 ** (row["attempt"] - 1))
        TaskRow.objects.using(self.db_alias).filter(id=row["id"]).update(
            status=TaskStatus.READY,
            run_after=timezone.now() + timedelta(seconds=delay),
            exception_class_path=f"{type(exc).__module__}.{type(exc).__qualname__}",
            traceback=str(exc)[:5000],
        )
        logger.warning(
            "tarea reintento id=%s attempt=%s/%s delay=%ss", row["id"], row["attempt"], row["max_attempts"], delay
        )

    def _fail(self, row: dict, error: str, *, exception_class_path: str = "") -> None:
        TaskRow.objects.using(self.db_alias).filter(id=row["id"]).update(
            status=TaskStatus.FAILED,
            exception_class_path=exception_class_path,
            traceback=error,
            finished_at=timezone.now(),
        )

    def _wait_for_notify(self) -> None:
        conn = self._connection.connection
        if conn is None:
            time.sleep(self.heartbeat_s)
            return
        # psycopg3 expone notifies como generator. Polleamos con select sobre el fd.
        try:
            r, _, _ = select.select([conn], [], [], self.heartbeat_s)
        except (OSError, ValueError):
            time.sleep(self.heartbeat_s)
            return
        if r:
            # Drenar notificaciones pendientes sin bloquear.
            for _ in conn.notifies(timeout=0):
                pass


def _is_json_serializable(v) -> bool:
    try:
        json.dumps(v)
        return True
    except (TypeError, ValueError):
        return False


def _coerce_json(value, default):
    """psycopg3 retorna JSONField como string cuando se accede vía raw cursor.

    Django ORM lo deserializa por nosotros, pero acá usamos
    ``UPDATE ... RETURNING`` en SQL crudo. Soportamos ambos casos."""
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default
