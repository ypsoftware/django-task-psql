# Configuration

Worker tuning is done via `TASK_WORKER_*` environment variables. All of them have sane defaults for local development — set them in production as needed.

| Variable | Default | Purpose |
|---|---|---|
| `TASK_WORKER_CONCURRENCY` | `1` | Threads processing tasks in parallel. |
| `TASK_WORKER_STALE_MINUTES` | `5` | A task stuck `RUNNING` (worker crash/OOM) is recovered to `READY` after this many minutes. |
| `TASK_WORKER_BACKOFF_BASE_S` | `30` | Base delay for exponential backoff between retries. |
| `TASK_WORKER_HEARTBEAT_S` | `5` | Fallback polling interval while waiting on `LISTEN`/`NOTIFY` (covers deferred tasks whose `run_after` has just elapsed). |
| `TASK_WORKER_DB_ALIAS` | `"default"` | Which `DATABASES` alias the worker connects through. Point this at a separate alias (with its own pool sized for `TASK_WORKER_CONCURRENCY + 1`) if you don't want the worker sharing a connection pool with your web process. |

A CLI flag (`--concurrency`, `--queues`) always overrides its corresponding environment variable.
