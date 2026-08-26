# How it works

- **Claiming**: `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING ...` — safe for multiple worker processes running in parallel.
- **Wakeup**: a Postgres trigger emits `NOTIFY task_psql_new` on every `INSERT` of a `READY` task (fired after commit, so tasks created inside a transaction only wake the worker once it commits). The worker blocks on `LISTEN` with a heartbeat fallback (`TASK_WORKER_HEARTBEAT_S`) to catch deferred tasks whose `run_after` has elapsed without a fresh `NOTIFY`.
- **Concurrency**: the worker's main thread claims one task at a time and submits it to a `ThreadPoolExecutor`; a `Semaphore` limits how many are in flight before claiming the next. Each thread closes its own database connection when it's done with a task — with Django's native connection pool enabled, that returns the connection to the pool instead of dropping the socket, which avoids a connection leak that recurring background threads are prone to.
- **Retries**: on failure, a task is rescheduled with `run_after = now() + backoff_base * 2^(attempt - 1)`, until `max_attempts` is reached, at which point it's marked `FAILED`.
