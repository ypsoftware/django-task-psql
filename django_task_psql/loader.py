"""Carga los módulos ``<app>.tasks`` de cada app instalada.

El decorador ``@task`` de ``django.tasks`` solo registra una función cuando el
módulo que la define se importa. En el proceso web eso pasa naturalmente (algo
importa el módulo para llamar ``.enqueue()``); el worker corre en un proceso
aparte que nunca llega a importar esos módulos por su cuenta, así que hay que
forzarlo al arrancar — igual que Celery autodiscover_tasks().
"""

import importlib
import logging

from django.apps import apps as django_apps

logger = logging.getLogger("django_task_psql")


def load_registered_tasks() -> None:
    for cfg in django_apps.get_app_configs():
        mod_name = f"{cfg.name}.tasks"
        try:
            importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue
        except Exception:
            logger.exception("error importando %s", mod_name)
