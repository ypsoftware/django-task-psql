"""Trigger PG: cada INSERT de una tarea READY emite NOTIFY task_psql_new.

El worker hace LISTEN sobre ese canal — wake-up inmediato sin polling.
``pg_notify`` se ejecuta en commit, no en insert, así que tareas creadas
dentro de una transacción solo despiertan al worker cuando la transacción
confirma.
"""

from django.db import migrations

CREATE_FN = """
CREATE OR REPLACE FUNCTION task_psql_notify() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('task_psql_new', NEW.queue_name);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

DROP_FN = "DROP FUNCTION IF EXISTS task_psql_notify() CASCADE;"

CREATE_TRG = """
CREATE TRIGGER task_psql_notify_trg
AFTER INSERT ON task_psql_task
FOR EACH ROW
WHEN (NEW.status = 'READY')
EXECUTE FUNCTION task_psql_notify();
"""

DROP_TRG = "DROP TRIGGER IF EXISTS task_psql_notify_trg ON task_psql_task;"


class Migration(migrations.Migration):
    dependencies = [
        ("django_task_psql", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_FN, reverse_sql=DROP_FN),
        migrations.RunSQL(sql=CREATE_TRG, reverse_sql=DROP_TRG),
    ]
