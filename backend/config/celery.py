"""Application Celery du backend (broker Redis).

Propagation de l'identifiant de requête : les producteurs passent
``headers={"request_id": ...}`` au moment de l'envoi ; la classe de base
``core.tasks.RequestIDTask`` lie cet identifiant au contexte structlog
pour toute la durée de la tâche, afin qu'il apparaisse dans les logs.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("emg_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Enregistre les tâches transverses (les apps métier seront auto-découvertes).
import core.tasks  # noqa: E402,F401
