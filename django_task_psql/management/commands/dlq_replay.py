"""Re-encola una o más tareas fallidas para que el worker las reintente.

Uso::

    python manage.py dlq_replay <id>           # re-encola una tarea
    python manage.py dlq_replay --all          # re-encola TODAS las fallidas
    python manage.py dlq_replay --all --queue emails  # solo fallidas de esa cola
"""

from django.core.management.base import BaseCommand, CommandError

from django_task_psql.models import TaskRow, TaskStatus


class Command(BaseCommand):
    help = "Re-encola tarea(s) fallida(s) para reintento (DLQ replay)."

    def add_arguments(self, parser):
        parser.add_argument("id", nargs="?", type=str, default=None, help="ID de la tarea a re-encolar.")
        parser.add_argument("--all", action="store_true", help="Re-encolar TODAS las fallidas.")
        parser.add_argument("--queue", type=str, default=None, help="Filtrar por cola (solo con --all).")

    def handle(self, *args, id, **opts):  # noqa: A002
        replay_all = opts.get("all", False)
        queue = opts.get("queue")

        if not id and not replay_all:
            raise CommandError("Especificá un <id> o usá --all.")
        if id and replay_all:
            raise CommandError("No podés usar <id> y --all al mismo tiempo.")

        if id:
            updated = TaskRow.objects.filter(id=id, status=TaskStatus.FAILED).update(
                status=TaskStatus.READY,
                attempt=0,
                exception_class_path="",
                traceback="",
            )
            if updated == 0:
                raise CommandError(f"Tarea {id!r} no encontrada o no está en estado FAILED.")
            self.stdout.write(self.style.SUCCESS(f"Tarea {id} re-encolada."))
            return

        qs = TaskRow.objects.filter(status=TaskStatus.FAILED)
        if queue:
            qs = qs.filter(queue_name=queue)
        count = qs.update(status=TaskStatus.READY, attempt=0, exception_class_path="", traceback="")
        queue_str = f" (queue={queue})" if queue else ""
        self.stdout.write(self.style.SUCCESS(f"{count} tarea(s) re-encolada(s){queue_str}."))
