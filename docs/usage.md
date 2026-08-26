# Usage

Standard `django.tasks` API — no custom decorator:

```python
from django.tasks import task

@task
def send_welcome_email(user_id):
    ...

send_welcome_email.enqueue(user_id)
```

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
