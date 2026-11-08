"""Services de la feature 03 (app ``audit``).

``record_event`` est le point d'entrée unique de l'audit : il est appelé par
les services de droits (``teams.services``) et par les vues de lecture des
données d'un sportif. Seules des données NON sensibles peuvent être passées
dans ``metadata`` (jamais d'email, mot de passe, jeton ou donnée médicale).

Décision : une erreur d'écriture d'audit ne casse jamais l'opération métier —
elle est loggée (``audit.record_failed``) pour remontée en observabilité.
"""

from __future__ import annotations

import structlog
from django.db.models.base import Model

from apps.audit.models import AuditEvent

logger = structlog.get_logger(__name__)


def record_event(
    actor,
    action: str,
    target: Model | None,
    athlete=None,
    metadata: dict | None = None,
    request=None,
) -> AuditEvent | None:
    """Enregistre un événement d'audit immuable.

    - ``actor`` : utilisateur à l'origine de l'action (obligatoire) ;
    - ``action`` : code stable machine-readable (ex. ``access_grant.created``) ;
    - ``target`` : instance Django ciblée (type et pk extraits automatiquement),
      ou ``None`` si l'action ne porte pas sur une ressource identifiable ;
    - ``athlete`` : profil sportif concerné (nullable) ;
    - ``metadata`` : dictionnaire JSON de contexte NON sensible ;
    - ``request`` : requête DRF/Django optionnelle (extrait IP + user agent).

    Retourne l'événement créé, ou ``None`` si l'écriture a échoué (loggée).
    """
    try:
        event = AuditEvent(
            actor=actor,
            action=action,
            target_type=type(target).__name__ if target is not None else "",
            target_id=getattr(target, "pk", None),
            athlete=athlete,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            metadata=metadata or {},
        )
        event.save()
        return event
    except Exception:  # noqa: BLE001 - l'audit ne doit jamais casser le métier
        logger.exception("audit.record_failed", action=action, actor_id=getattr(actor, "pk", None))
        return None


def _client_ip(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _user_agent(request) -> str:
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:512]
