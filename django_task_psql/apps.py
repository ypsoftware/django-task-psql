from django.apps import AppConfig


class DjangoTaskPsqlConfig(AppConfig):
    name = "django_task_psql"
    label = "django_task_psql"
    verbose_name = "Task Queue (Postgres)"
    default_auto_field = "django.db.models.BigAutoField"
