"""Sélecteurs de lecture de la feature 06 (app ``sessions``).

Toute autorisation passe par le module central ``core.access`` (décision
d'architecture n°8) — jamais de requête directe sur les grants ici :
- le PROPRIÉTAIRE du profil sportif voit toutes les séances de son athlète,
  lecture et écriture ;
- un coach / membre d'équipe accède aux séances RATTACHÉES à ses sportifs si
  un grant actif (statut ``active`` ET non expiré — vérifié dans
  ``core.access``, au niveau du sélecteur) porte le scope adéquat sur le
  profil du sportif ;
- un superutilisateur Django voit tout (usage opérationnel/administratif).

Décision documentée : la LECTURE des séances réutilise le scope existant
``sessions:read`` et l'ÉCRITURE (création, transitions de statut, annotations)
le scope ``sessions:write`` — aucun nouveau scope n'est créé dans
``core.scopes``. Le créateur d'une séance (``created_by``) n'a pas de droit
particulier : ses droits restent ceux qu'il a sur le profil du sportif — un
coach qui crée une séance pour son sportif la voit ensuite via son grant, pas
via sa qualité de créateur.
"""

from django.db.models import QuerySet

from core import access, scopes


def visible_sessions(user) -> QuerySet:
    """Séances visibles par ``user`` (sélecteur de liste).

    Base de ``GET /api/v1/sessions/`` : séances dont le sportif est soit
    propriété de l'utilisateur, soit couvert par un grant actif portant le
    scope ``sessions:read``.
    """
    from apps.sessions.models import Session

    qs = Session.objects.all()
    if user is None or not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser:
        return qs
    athlete_ids = access.visible_athletes(user, scopes.SESSIONS_READ.name).values_list(
        "pk", flat=True
    )
    return qs.filter(athlete_id__in=athlete_ids).distinct()


def can_read_session(user, session) -> bool:
    """Lecture d'une séance : propriétaire du profil, superutilisateur, ou grant.

    Pour un non-propriétaire, l'accès exige un grant ``sessions:read`` actif et
    non expiré portant sur le profil du sportif (vérifié par
    ``core.access.can_access_athlete`` — point de contrôle unique).
    """
    return access.can_access_athlete(user, session.athlete, scopes.SESSIONS_READ.name)


def can_write_session(user, session) -> bool:
    """Écriture sur une séance (transitions, annotations) : scope ``sessions:write``.

    Pour un non-propriétaire, l'accès exige un grant ``sessions:write`` actif et
    non expiré portant sur le profil du sportif. Un grant ``sessions:read``
    n'ouvre PAS l'écriture (un scope ne déborde jamais sur un autre, cf.
    ``core.access``).
    """
    return access.can_access_athlete(user, session.athlete, scopes.SESSIONS_WRITE.name)
