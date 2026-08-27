# Usage

Standard `django.tasks` API — no custom decorator:

```python
from django.tasks import task

@task
def send_welcome_email(user_id):
    ...

send_welcome_email.enqueue(user_id)
```

Per-task retry override: `@task(queue_name="emails", max_attempts=1)`. Overrides `OPTIONS["max_attempts"]` for that task only; tasks that don't set it keep using the backend-wide default.

Coroutines (`async def`) work out of the box — `Task.call()` bridges them via `async_to_sync` internally, no asyncio event loop needed in the worker.

## Running the worker

```bash
python manage.py runworker --queues default emails --concurrency 4
```

- `--batch`: drain the queue then exit (useful for a Kubernetes Job).
- `--max-tasks N`: exit after roughly N tasks.
- `--backend default`: which `TASKS` alias to process.

## Django admin

`TaskRow` is registered read-only in the Django admin for inspection.

## OpenTelemetry (optional)

```bash
pip install django-task-psql[otel]
```

Installing the `otel` extra (`opentelemetry-api` only) wraps every task execution in a span named `<TASK_WORKER_SPAN_PREFIX>.<task_path>` (attributes: `django_task_psql.attempt`, `django_task_psql.queue_name`), with exceptions recorded and the span marked as an error. Nothing is exported unless your app configures a `TracerProvider` and exporter itself (e.g. `opentelemetry-sdk` + an OTLP exporter); without `opentelemetry-api` installed at all, tracing is skipped entirely with zero import errors.
