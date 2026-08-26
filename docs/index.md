# django-task-psql

A Postgres-native backend for [Django Tasks](https://docs.djangoproject.com/en/stable/topics/tasks/) (`django.tasks`, Django 6.0+).

Django 6.0 introduced an official interface for background task queues (`@task`, `.enqueue()`, pluggable backends via the `TASKS` setting). `django-task-psql` is a production backend for that interface, built specifically for Postgres: real queueing via `SKIP LOCKED`, `LISTEN`/`NOTIFY` wakeup instead of polling, and automatic retries with exponential backoff — no Celery or Redis required.

Built Postgres-only on purpose, trading multi-engine support for tighter integration with Postgres features (see [`django-tasks-db`](https://github.com/RealOrangeOne/django-tasks-db) for a database-agnostic alternative).

```{toctree}
:maxdepth: 2
:caption: Contents

installation
usage
configuration
management-commands
architecture
scope
```

## License

MIT
