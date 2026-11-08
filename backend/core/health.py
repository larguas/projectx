"""Vérifications de santé du service : application, base de données, Redis."""

import structlog
from django.db import connections

logger = structlog.get_logger(__name__)


def check_app() -> str:
    """L'application répond : c'est par définition OK."""
    return "ok"


def check_database() -> str:
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        return "ok"
    except Exception:  # noqa: BLE001 - toute panne DB doit rester lisible dans le health.
        logger.warning("health.database.error", exc_info=True)
        return "error"


def check_redis() -> str:
    try:
        from core.redis_client import get_redis_client

        get_redis_client().ping()
        return "ok"
    except Exception:  # noqa: BLE001 - idem : le health doit toujours répondre.
        logger.warning("health.redis.error", exc_info=True)
        return "error"


def run_checks() -> dict[str, str]:
    return {
        "app": check_app(),
        "database": check_database(),
        "redis": check_redis(),
    }
