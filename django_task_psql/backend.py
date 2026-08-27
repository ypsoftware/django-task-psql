"""Backend de ``django.tasks`` respaldado por Postgres.

Ver ``django.tasks.backends.immediate.ImmediateBackend`` — este backend
espeja su forma de construir/mutar un ``TaskResult`` en vez de reinventarla.
"""

import uuid
from dataclasses import dataclass

from django.tasks.backends.base import BaseTaskBackend
from django.tasks.base import Task, TaskError, TaskResult, TaskResultStatus
from django.tasks.exceptions import TaskResultDoesNotExist
from django.utils import timezone
from django.utils.json import normalize_json
from django.utils.module_loading import import_string

# Dotted path -> Task registrado en este proceso. Se puebla cuando el @task de
# django.tasks decora una función con este backend (ver PostgresTask.__post_init__)
# y también al reimportar un módulo de tasks explícitamente (ver _resolve_task).
REGISTRY: dict[str, Task] = {}


@dataclass(frozen=True, slots=True, kw_only=True)
class PostgresTask(Task):
    """Subclase de ``Task`` que se auto-registra al crearse.

    ``task_class`` es el punto de extensión que ``django.tasks`` expone justo
    para esto: el decorador ``@task`` llama ``task_backends[backend].task_class(...)``,
    reenviando ``**kwargs`` sin filtrar — por eso ``@task(max_attempts=1)`` ya
    funciona hoy sin ningún cambio en Django.

    ``max_attempts=None`` (default) significa "usar el valor de
    ``OPTIONS.max_attempts`` del backend" — ver ``PostgresBackend.enqueue()``.
    """

    max_attempts: int | None = None

    def __post_init__(self):
        super().__post_init__()
        REGISTRY[self.module_path] = self


class PostgresBackend(BaseTaskBackend):
    task_class = PostgresTask

    supports_defer = True
    supports_async_task = True
    supports_priority = True
    supports_get_result = True

    def __init__(self, alias, params):
        super().__init__(alias, params)
        id_function = self.options.get("id_function")
        if id_function is None:
            self.id_function = uuid.uuid4
        elif callable(id_function):
            self.id_function = id_function
        else:
            self.id_function = import_string(id_function)

    def _resolve_task(self, task_path: str) -> Task | None:
        task = REGISTRY.get(task_path)
        if task is not None:
            return task
        # El módulo puede no estar importado en este proceso (ej. get_result()
        # llamado desde un proceso que nunca importó ese módulo de tasks).
        # import_string importa el módulo y accede al atributo, lo que corre
        # el decorador @task y puebla el REGISTRY como efecto colateral.
        try:
            import_string(task_path)
        except ImportError:
            return None
        return REGISTRY.get(task_path)

    def enqueue(self, task: Task, args, kwargs) -> TaskResult:
        self.validate_task(task)

        from .models import TaskRow

        row = TaskRow.objects.create(
            id=self.id_function(),
            queue_name=task.queue_name,
            task_path=task.module_path,
            args=normalize_json(list(args)),
            kwargs=normalize_json(kwargs),
            priority=task.priority,
            run_after=task.run_after or timezone.now(),
            max_attempts=task.max_attempts if task.max_attempts is not None else self.options.get("max_attempts", 1),
            backend_name=self.alias,
        )
        return self._to_task_result(row, task)

    def get_result(self, result_id: str) -> TaskResult:
        from .models import TaskRow

        try:
            row = TaskRow.objects.get(id=result_id)
        except (TaskRow.DoesNotExist, ValueError, TypeError) as e:
            raise TaskResultDoesNotExist(result_id) from e

        task = self._resolve_task(row.task_path)
        return self._to_task_result(row, task)

    def _to_task_result(self, row, task: Task | None) -> TaskResult:
        from .models import TaskStatus

        errors = []
        if row.status == TaskStatus.FAILED and row.exception_class_path:
            errors.append(TaskError(exception_class_path=row.exception_class_path, traceback=row.traceback))

        result = TaskResult(
            task=task,
            id=str(row.id),
            status=TaskResultStatus[row.status],
            enqueued_at=row.enqueued_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            last_attempted_at=row.started_at,
            args=row.args,
            kwargs=row.kwargs,
            backend=row.backend_name,
            errors=errors,
            worker_ids=row.worker_ids,
        )
        object.__setattr__(result, "_return_value", row.return_value)
        return result
