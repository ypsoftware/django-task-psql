"""Borra tareas completadas/fallidas viejas. Pensado para cron.

python manage.py cleanup_tasks --days 7
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from django_task_psql.models import TaskRow, TaskStatus


class Command(BaseCommand):
    help = "Borra tareas completadas o fallidas finalizadas hace más de N días."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, days, **opts):
        cutoff = timezone.now() - timedelta(days=days)
        qs = TaskRow.objects.filter(
            status__in=[TaskStatus.SUCCESSFUL, TaskStatus.FAILED],
            finished_at__lt=cutoff,
        )
        n, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Borradas {n} tareas anteriores a {cutoff.isoformat()}"))
