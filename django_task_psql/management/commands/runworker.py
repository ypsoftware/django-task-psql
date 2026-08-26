from django.core.management.base import BaseCommand, CommandError

from django_task_psql.worker import Worker


class Command(BaseCommand):
    help = "Worker de django_task_psql. Procesa tareas encoladas en Postgres."

    def add_arguments(self, parser):
        parser.add_argument(
            "--queues",
            nargs="+",
            default=["default"],
            help="Lista de colas a consumir. Default: ['default'].",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=None,
            help="Tareas ejecutándose en paralelo (thread pool). Override de TASK_WORKER_CONCURRENCY.",
        )
        parser.add_argument(
            "--backend",
            dest="backend_alias",
            default="default",
            help="Alias del backend en TASKS a procesar. Default: 'default'.",
        )
        parser.add_argument(
            "--batch",
            action="store_true",
            help="Procesa todas las tareas pendientes y sale, en vez de quedar corriendo.",
        )
        parser.add_argument(
            "--max-tasks",
            type=int,
            default=None,
            help="Corte: máximo de tareas a ejecutar antes de salir.",
        )

    def handle(self, *args, queues, concurrency, backend_alias, batch, max_tasks, **opts):
        if concurrency is not None and concurrency < 1:
            raise CommandError("--concurrency debe ser >= 1")
        Worker(
            queues=queues,
            concurrency=concurrency,
            backend_alias=backend_alias,
            batch=batch,
            max_tasks=max_tasks,
        ).run()
