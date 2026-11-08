"""Tâches Celery transverses.

Propagation de l'identifiant de requête : le producteur envoie la tâche avec
``headers={"request_id": ...}`` ; ``RequestIDTask`` le lie au contexte
structlog pendant toute la durée de l'exécution (logs structurés).
"""

import structlog
from celery import Task, shared_task

logger = structlog.get_logger(__name__)


class RequestIDTask(Task):
    """Base de tâche : lie l'identifiant de requête des headers aux logs."""

    abstract = True

    def run(self, *args, **kwargs):
        headers = getattr(self.request, "headers", None) or {}
        request_id = headers.get("request_id")
        structlog.contextvars.clear_contextvars()
        if request_id:
            structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            return super().run(*args, **kwargs)
        finally:
            structlog.contextvars.clear_contextvars()


@shared_task(bind=True, base=RequestIDTask, name="core.ping")
def ping(self):
    """Tâche d'exemple : vérifie que le broker et les workers répondent."""
    logger.info("task.ping.completed", task_id=self.request.id)
    return "pong"
