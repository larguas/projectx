"""Handler d'exceptions DRF : format d'erreur unique pour toute l'API.

Format renvoyé sur toutes les erreurs :

.. code-block:: json

    {
      "error": {
        "code": "validation_error",
        "message": "La demande est invalide.",
        "details": {"email": ["Ce champ est obligatoire."]}
      }
    }

``code`` est stable et machine-readable ; ``details`` contient les erreurs
par champ (validation) ou est ``null``.
"""

import structlog
from django.db import IntegrityError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = structlog.get_logger(__name__)

# Statut HTTP -> (code stable, message par défaut).
_STATUS_MESSAGES: dict[int, tuple[str, str]] = {
    400: ("validation_error", "La demande est invalide."),
    401: ("authentication_required", "Authentification requise ou jeton invalide."),
    403: ("permission_denied", "Accès refusé."),
    404: ("not_found", "Ressource introuvable."),
    405: ("method_not_allowed", "Méthode non autorisée sur cette ressource."),
    409: ("conflict", "Conflit avec l'état actuel de la ressource."),
    415: ("unsupported_media_type", "Type de média non supporté."),
    426: ("upgrade_required", "La version du client est trop ancienne."),
    429: ("rate_limited", "Trop de requêtes, réessayez plus tard."),
    500: ("server_error", "Une erreur interne est survenue."),
}


def _error_response(
    status_code: int,
    code: str | None = None,
    message: str | None = None,
    details: object = None,
) -> Response:
    default_code, default_message = _STATUS_MESSAGES.get(status_code, ("error", "Erreur."))
    return Response(
        {
            "error": {
                "code": code or default_code,
                "message": message or default_message,
                "details": details,
            }
        },
        status=status_code,
    )


def drf_exception_handler(exc: Exception, context: dict) -> Response:
    """Transforme toute exception en ErrorResponse (format unique)."""
    request = context.get("request")
    path = getattr(request, "path", None)

    # Conflit d'intégrité (doublon, contrainte) -> 409 plutôt que 500.
    if isinstance(exc, IntegrityError):
        logger.warning("api.conflict", path=path)
        return _error_response(409)

    response = exception_handler(exc, context)
    if response is not None:
        code, message = _STATUS_MESSAGES.get(response.status_code, ("error", "Erreur."))
        data = response.data
        details = data if isinstance(data, (dict, list)) else None
        return _error_response(response.status_code, code, message, details)

    # Exception non gérée : log structuré (avec request_id) + Sentry.
    logger.exception("api.unhandled_exception", path=path)
    import sentry_sdk

    sentry_sdk.capture_exception(exc)
    return _error_response(500)
