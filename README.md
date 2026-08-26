# django-task-psql

A Postgres-native backend for [Django Tasks](https://docs.djangoproject.com/en/stable/topics/tasks/) (`django.tasks`, Django 6.0+).

Django 6.0 introduced an official interface for background task queues (`@task`, `.enqueue()`, pluggable backends via the `TASKS` setting), but ships with only two backends: `ImmediateBackend` (runs synchronously, no real queue) and `DummyBackend` (tests only). `django-task-psql` fills that gap for Postgres users who don't want to run Celery or Redis.

## Why not just use [`django-tasks-db`](https://github.com/RealOrangeOne/django-tasks-db)?

That project is mature and database-agnostic (Postgres/MySQL/SQLite). `django-task-psql` makes the opposite trade-off: **Postgres-only**, in exchange for two things that engine-agnostic design can't give you:

- **`LISTEN`/`NOTIFY` wakeup** instead of polling — the worker reacts to a new task almost instantly instead of waiting for the next poll interval.
- **Automatic retries with exponential backoff** — a failing task is retried up to `max_attempts` times with an increasing delay, not just marked `FAILED` after the first error.

Both projects use `SKIP LOCKED` for claiming; both are valid choices depending on whether you need multi-engine support.

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
python manage.py dlq_list
python manage.py dlq_replay <id>
python manage.py dlq_replay --all --queue emails
python manage.py stats --days 7
python manage.py cleanup_tasks --days 7   # prune old finished rows, e.g. from cron
```

### Django admin

`TaskRow` is registered read-only in the Django admin for inspection.

## How it works

- **Claiming**: `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING ...` — safe for multiple worker processes running in parallel.
- **Wakeup**: a Postgres trigger emits `NOTIFY task_psql_new` on every `INSERT` of a `READY` task (fired after commit, so tasks created inside a transaction only wake the worker once it commits). The worker blocks on `LISTEN` with a heartbeat fallback (`TASK_WORKER_HEARTBEAT_S`) to catch deferred tasks whose `run_after` has elapsed without a fresh `NOTIFY`.
- **Concurrency**: the worker's main thread claims one task at a time and submits it to a `ThreadPoolExecutor`; a `Semaphore` limits how many are in flight before claiming the next. Each thread closes its own database connection when it's done with a task — with Django's native connection pool enabled, that returns the connection to the pool instead of dropping the socket, which avoids a connection leak that recurring background threads are prone to.
- **Retries**: on failure, a task is rescheduled with `run_after = now() + backoff_base * 2^(attempt - 1)`, until `max_attempts` is reached, at which point it's marked `FAILED`.

## Scope

Postgres only — no MySQL/SQLite compatibility layer, no support for Django versions before 6.0 (i.e. before `django.tasks` existed). Single Postgres-cluster deployments only; the design (`SKIP LOCKED`) supports running multiple worker processes in parallel already, though that hasn't been load-tested yet.

## License

MIT
