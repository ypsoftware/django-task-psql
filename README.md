# django-task-psql

A Postgres-native backend for [Django Tasks](https://docs.djangoproject.com/en/stable/topics/tasks/) (`django.tasks`, Django 6.0+).

Django 6.0 introduced an official interface for background task queues (`@task`, `.enqueue()`, pluggable backends via the `TASKS` setting). `django-task-psql` is a production backend for that interface, built specifically for Postgres: real queueing via `SKIP LOCKED`, `LISTEN`/`NOTIFY` wakeup instead of polling, and automatic retries with exponential backoff — no Celery or Redis required.

Built Postgres-only on purpose, trading multi-engine support for tighter integration with Postgres features (see [`django-tasks-db`](https://github.com/RealOrangeOne/django-tasks-db) for a database-agnostic alternative).

## Installation

```bash
pip install django-task-psql
```

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

```bash
python manage.py migrate
```

## Usage

Standard `django.tasks` API — no custom decorator:

```python
from django.tasks import task

@task
def send_welcome_email(user_id):
    ...

send_welcome_email.enqueue(user_id)
```

Coroutines (`async def`) work out of the box — `Task.call()` bridges them via `async_to_sync` internally, no asyncio event loop needed in the worker.

### Running the worker

```bash
python manage.py runworker --queues default emails --concurrency 4
```

- `--batch`: drain the queue then exit (useful for a Kubernetes Job).
- `--max-tasks N`: exit after roughly N tasks.
- `--backend default`: which `TASKS` alias to process.

### Configuration via environment variables

All of these have sane defaults for local development — set them in production as needed:

| Variable | Default | Purpose |
|---|---|---|
| `TASK_WORKER_CONCURRENCY` | `1` | Threads processing tasks in parallel. |
| `TASK_WORKER_STALE_MINUTES` | `5` | A task stuck `RUNNING` (worker crash/OOM) is recovered to `READY` after this many minutes. |
| `TASK_WORKER_BACKOFF_BASE_S` | `30` | Base delay for exponential backoff between retries. |
| `TASK_WORKER_HEARTBEAT_S` | `5` | Fallback polling interval while waiting on `LISTEN`/`NOTIFY` (covers deferred tasks whose `run_after` has just elapsed). |
| `TASK_WORKER_DB_ALIAS` | `"default"` | Which `DATABASES` alias the worker connects through. Point this at a separate alias (with its own pool sized for `TASK_WORKER_CONCURRENCY + 1`) if you don't want the worker sharing a connection pool with your web process. |

A CLI flag (`--concurrency`, `--queues`) always overrides its corresponding environment variable.

### Dead-letter queue

```bash
python manage.py dlq_list                    # all failed tasks
python manage.py dlq_list --queue emails --limit 50
python manage.py dlq_list --json

python manage.py dlq_replay <id>             # requeue one failed task
python manage.py dlq_replay --all --queue emails

python manage.py stats --days 7              # queue stats: totals + top failing tasks
python manage.py stats --queue emails --json

python manage.py cleanup_tasks --days 7      # prune old finished rows, e.g. from cron
```

### Django admin

`TaskRow` is registered read-only in the Django admin for inspection.

## How it works

- **Claiming**: `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING ...` — safe for multiple worker processes running in parallel.
- **Wakeup**: a Postgres trigger emits `NOTIFY task_psql_new` on every `INSERT` of a `READY` task (fired after commit, so tasks created inside a transaction only wake the worker once it commits). The worker blocks on `LISTEN` with a heartbeat fallback (`TASK_WORKER_HEARTBEAT_S`) to catch deferred tasks whose `run_after` has elapsed without a fresh `NOTIFY`.
- **Concurrency**: the worker's main thread claims one task at a time and submits it to a `ThreadPoolExecutor`; a `Semaphore` limits how many are in flight before claiming the next. Each thread closes its own database connection when it's done with a task — with Django's native connection pool enabled, that returns the connection to the pool instead of dropping the socket, which avoids a connection leak that recurring background threads are prone to.
- **Retries**: on failure, a task is rescheduled with `run_after = now() + backoff_base * 2^(attempt - 1)`, until `max_attempts` is reached, at which point it's marked `FAILED`.

## Scope

Targets Postgres and Django 6.0+. Designed for a single Postgres cluster; `SKIP LOCKED` already supports running multiple worker processes against it in parallel.

## License

MIT
