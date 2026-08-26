# Management commands

## Dead-letter queue

```bash
python manage.py dlq_list                    # all failed tasks
python manage.py dlq_list --queue emails --limit 50
python manage.py dlq_list --json

python manage.py dlq_replay <id>             # requeue one failed task
python manage.py dlq_replay --all --queue emails
```

## Stats

```bash
python manage.py stats --days 7              # queue stats: totals + top failing tasks
python manage.py stats --queue emails --json
```

## Cleanup

```bash
python manage.py cleanup_tasks --days 7      # prune old finished rows, e.g. from cron
```
