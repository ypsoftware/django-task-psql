"""Tasks de prueba — importado por el loader del worker vía load_registered_tasks()."""

import threading

from django.tasks import task


@task(queue_name="test-ok")
def ok_task(x):
    return x * 2


@task(queue_name="test-fail")
def always_fails():
    raise RuntimeError("boom")


@task(queue_name="test-ok", max_attempts=5)
def task_max_attempts_5(x):
    return x


@task(queue_name="test-ok")
def not_serializable():
    class X:
        pass

    return X()


slow_started = threading.Event()
slow_continue = threading.Event()


@task(queue_name="test-concurrency")
def slow_task():
    slow_started.set()
    slow_continue.wait(timeout=5)
    return "done"


@task(queue_name="test-ok")
async def async_task(x):
    return x + 1
