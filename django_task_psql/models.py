import uuid

from django.db import models
from django.utils import timezone


class TaskStatus(models.TextChoices):
    """Espeja ``django.tasks.base.TaskResultStatus`` — mismos nombres, para
    convertir a ``TaskResult`` sin tabla de mapeo."""

    READY = "READY", "Ready"
    RUNNING = "RUNNING", "Running"
    SUCCESSFUL = "SUCCESSFUL", "Successful"
    FAILED = "FAILED", "Failed"


class TaskRow(models.Model):
    """Una tarea encolada en Postgres."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    queue_name = models.CharField(max_length=40, default="default")
    task_path = models.TextField(help_text="Dotted path: app.tasks.funcion")
    args = models.JSONField(default=list, blank=True)
    kwargs = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.READY)
    priority = models.IntegerField(default=0)

    run_after = models.DateTimeField(default=timezone.now)
    attempt = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=1)

    exception_class_path = models.TextField(blank=True, default="")
    traceback = models.TextField(blank=True, default="")
    return_value = models.JSONField(null=True, blank=True, default=None)
    worker_ids = models.JSONField(default=list, blank=True)

    enqueued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    backend_name = models.CharField(max_length=32, default="default")

    class Meta:
        db_table = "task_psql_task"
        ordering = ["-priority", "run_after"]
        indexes = [
            # Parcial: scan barato para el claim aunque la tabla crezca.
            models.Index(
                fields=["queue_name", "priority", "run_after"],
                name="task_psql_ready_idx",
                condition=models.Q(status="READY"),
            ),
            models.Index(fields=["status", "finished_at"], name="task_psql_cleanup_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.task_path} [{self.status}]"
