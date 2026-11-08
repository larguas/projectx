"""Configuration des logs structurés (structlog).

JSON en production, rendu lisible en développement. L'identifiant de
requête (lié par ``core.middleware.RequestIDMiddleware`` ou par les tâches
Celery via ``core.tasks.RequestIDTask``) apparaît dans toutes les entrées
grâce à ``merge_contextvars``. Les logs stdlib (Django, DRF, ...) passent
par le même formatteur.
"""

import logging
import sys

import structlog


def configure_logging(debug: bool, level: str = "INFO") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    pre_chain = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        timestamper,
    ]
    renderer = (
        structlog.dev.ConsoleRenderer(colors=False)
        if debug
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=pre_chain,
    )
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[handler], force=True)
