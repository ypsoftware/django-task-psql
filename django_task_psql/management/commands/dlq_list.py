"""Lista tareas fallidas (dead-letter queue).

Uso::

    python manage.py dlq_list                    # todas las fallidas
    python manage.py dlq_list --queue emails
    python manage.py dlq_list --limit 50
    python manage.py dlq_list --json
"""

import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from django_task_psql.models import TaskRow, TaskStatus


class Command(BaseCommand):
    help = "Lista tareas fallidas en django_task_psql (DLQ view)."

    def add_arguments(self, parser):
        parser.add_argument("--queue", type=str, default=None, help="Filtrar por cola.")
        parser.add_argument("--limit", type=int, default=20, help="Máximo de filas (default 20).")
        parser.add_argument("--json", action="store_true", help="Output JSON.")

    def handle(self, *args, queue, limit, **opts):
        output_json = opts.get("json", False)
        qs = TaskRow.objects.filter(status=TaskStatus.FAILED).order_by("-finished_at")
        if queue:
            qs = qs.filter(queue_name=queue)
        rows = list(
            qs[:limit].values(
                "id", "queue_name", "task_path", "attempt", "max_attempts", "exception_class_path", "traceback",
                "enqueued_at", "finished_at",
            )
        )

        if output_json:
            self.stdout.write(json.dumps(rows, default=str, ensure_ascii=False))
            return

        if not rows:
            self.stdout.write(self.style.SUCCESS("No hay tareas fallidas."))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f"{len(rows)} tarea(s) fallida(s):"))
        for r in rows:
            age = timezone.now() - (r["finished_at"] or timezone.now())
            self.stdout.write(
                f"  {r['id']}  queue={r['queue_name']}  task={r['task_path']}"
                f"  attempts={r['attempt']}/{r['max_attempts']}"
                f"  hace={int(age.total_seconds() // 60)}m"
            )
            if r["exception_class_path"]:
                self.stdout.write(f"    {r['exception_class_path']}: {r['traceback'][:120]}")
        self.stdout.write("\nPara re-encolar: manage.py dlq_replay <id>")
