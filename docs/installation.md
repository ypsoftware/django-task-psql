# Installation

```bash
pip install django-task-psql
```

Add the app and configure the `TASKS` backend:

```python
INSTALLED_APPS = [
    ...,
    "django_task_psql",
]

TASKS = {
    "default": {
        "BACKEND": "django_task_psql.backend.PostgresBackend",
        "QUEUES": ["default"],
        "OPTIONS": {
            # Optional. Defaults to uuid.uuid4.
            "id_function": "uuid.uuid4",
            # Optional. Default attempts before a task is marked FAILED. Defaults to 1.
            "max_attempts": 3,
        },
    }
}
```

Run the migrations to create the task table and the `NOTIFY` trigger:

```bash
python manage.py migrate
```
