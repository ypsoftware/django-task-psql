import uuid

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="TaskRow",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("queue_name", models.CharField(default="default", max_length=40)),
                ("task_path", models.TextField(help_text="Dotted path: app.tasks.funcion")),
                ("args", models.JSONField(blank=True, default=list)),
                ("kwargs", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("READY", "Ready"),
                            ("RUNNING", "Running"),
                            ("SUCCESSFUL", "Successful"),
                            ("FAILED", "Failed"),
                        ],
                        default="READY",
                        max_length=20,
                    ),
                ),
                ("priority", models.IntegerField(default=0)),
                ("run_after", models.DateTimeField(default=django.utils.timezone.now)),
                ("attempt", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=1)),
                ("exception_class_path", models.TextField(blank=True, default="")),
                ("traceback", models.TextField(blank=True, default="")),
                ("return_value", models.JSONField(blank=True, default=None, null=True)),
                ("worker_ids", models.JSONField(blank=True, default=list)),
                ("enqueued_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("backend_name", models.CharField(default="default", max_length=32)),
            ],
            options={
                "db_table": "task_psql_task",
                "ordering": ["-priority", "run_after"],
                "indexes": [
                    models.Index(
                        condition=models.Q(("status", "READY")),
                        fields=["queue_name", "priority", "run_after"],
                        name="task_psql_ready_idx",
                    ),
                    models.Index(fields=["status", "finished_at"], name="task_psql_cleanup_idx"),
                ],
            },
        ),
    ]
