"""Stats de la cola — útil para auditar en server sin depender de un dashboard externo.

Uso::

    python manage.py stats                  # últimos 7 días
    python manage.py stats --days 30
    python manage.py stats --queue emails --days 1
    python manage.py stats --json           # output JSON para scrape
"""

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from django_task_psql.models import TaskRow, TaskStatus


class Command(BaseCommand):
    help = "Estadísticas de la cola de tareas (django_task_psql)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--queue", type=str, default=None, help="Filtrar por cola.")
        parser.add_argument("--json", action="store_true", help="Output JSON.")

    def handle(self, *args, days, queue, json: bool, **opts):
        since = timezone.now() - timedelta(days=days)
        qs = TaskRow.objects.filter(enqueued_at__gte=since)
        if queue:
            qs = qs.filter(queue_name=queue)

        totals = _totals(qs)
        top_errors = _top_errors(qs, limit=5)

        data = {
            "window_days": days,
            "queue": queue or "all",
            "totals": totals,
            "top_errors": top_errors,
        }

        if json:
            self.stdout.write(_json_dumps(data))
            return
        self._render_text(data)

    def _render_text(self, d: dict) -> None:
        self.stdout.write(
            self.style.MIGRATE_HEADING(f"django_task_psql stats — últimos {d['window_days']} días — queue={d['queue']}")
        )
        t = d["totals"]
        self.stdout.write(
            f"  enqueued={t['enqueued']}  successful={t['successful']}  "
            f"failed={t['failed']}  ready={t['ready']}  running={t['running']}"
        )
        if t["successful"] + t["failed"]:
            failure_rate = 100 * t["failed"] / max(t["successful"] + t["failed"], 1)
            self.stdout.write(f"  tasa de fallo: {failure_rate:.1f}%")

        if d["top_errors"]:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("Top 5 tasks con más errores"))
            for row in d["top_errors"]:
                self.stdout.write(f"  {row['n']:>4}  {row['task_path']}")


def _totals(qs) -> dict:
    agg = qs.aggregate(
        enqueued=Count("id"),
        successful=Count("id", filter=Q(status=TaskStatus.SUCCESSFUL)),
        failed=Count("id", filter=Q(status=TaskStatus.FAILED)),
        ready=Count("id", filter=Q(status=TaskStatus.READY)),
        running=Count("id", filter=Q(status=TaskStatus.RUNNING)),
    )
    return {k: v or 0 for k, v in agg.items()}


def _top_errors(qs, limit: int):
    rows = (
        qs.filter(status=TaskStatus.FAILED)
        .values("task_path")
        .annotate(n=Count("id"))
        .order_by("-n")[:limit]
    )
    return [{"task_path": r["task_path"], "n": r["n"]} for r in rows]


def _json_dumps(d: dict) -> str:
    return json.dumps(d, indent=2, default=str)
