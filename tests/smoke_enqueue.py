"""Encola una tarea y espera a que termine — para usar junto con un
``runworker`` corriendo en otro proceso (ver smoke test manual del LISTEN/NOTIFY)."""

import os
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
django.setup()

from django_task_psql.models import TaskRow, TaskStatus  # noqa: E402
from tests import tasks  # noqa: E402


def main():
    TaskRow.objects.all().delete()
    start = time.monotonic()
    result = tasks.ok_task.enqueue(21)
    print(f"enqueued {result.id}")

    row = None
    while time.monotonic() - start < 10:
        row = TaskRow.objects.get(id=result.id)
        if row.status in (TaskStatus.SUCCESSFUL, TaskStatus.FAILED):
            break
        time.sleep(0.05)

    elapsed = time.monotonic() - start
    print(f"status={row.status} return_value={row.return_value} elapsed={elapsed:.3f}s")
    assert row.status == TaskStatus.SUCCESSFUL, f"tarea no completo OK: {row.status} {row.traceback}"
    assert row.return_value == 42
    assert elapsed < 2.0, f"tardo {elapsed:.3f}s — sospechoso de estar cayendo al polling fallback, no a NOTIFY"
    print("OK: LISTEN/NOTIFY funciona, wakeup fue casi instantaneo")


if __name__ == "__main__":
    main()
