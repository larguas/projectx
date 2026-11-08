"""Sélecteurs de lecture de la feature 05 (app ``workouts``).

Toute autorisation passe par le module central ``core.access`` (décision
d'architecture n°8) — jamais de requête directe sur les grants ici :
- le PROPRIÉTAIRE d'un plan (``owner``) y accède toujours, lecture et écriture ;
- un coach / membre d'équipe accède aux plans RATTACHÉS à ses sportifs si un
  grant actif (statut ``active`` ET non expiré — vérifié dans ``core.access``,
  au niveau du sélecteur) porte le scope adéquat sur le profil du sportif ;
- un plan SANS athlète (``athlete=None``) n'est accessible que par son
  propriétaire : un coach ne peut pas « adopter » un plan orphelin, même avec
  un grant actif ;
- un superutilisateur Django voit tout (usage opérationnel/administratif).

Décision documentée (spec feature 05 : « scope ``sessions:read`` / écriture
selon besoin, à documenter ») : la LECTURE des plans réutilise le scope
existant ``sessions:read`` et l'ÉCRITURE (PATCH/PUT/DELETE) le scope
``sessions:write`` — aucun nouveau scope n'est créé dans ``core.scopes`` : un
plan d'entraînement est la donnée de travail des séances, exactement ce que
ces deux scopes couvrent déjà.
"""

from django.db.models import Q, QuerySet

from core import access, scopes


def visible_workouts(user) -> QuerySet:
    """Plans visibles par ``user`` (sélecteur de liste).

    Base de ``GET /api/v1/workouts/`` : plans dont le propriétaire est
    l'utilisateur lui-même, ou rattachés à un de ses sportifs couverts par un
    grant actif portant le scope ``sessions:read``.
    """
    from apps.workouts.models import Workout

    qs = Workout.objects.all()
    if user is None or not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser:
        return qs
    granted_athlete_ids = access.visible_athletes(user, scopes.SESSIONS_READ.name).values_list(
        "pk", flat=True
    )
    return qs.filter(Q(owner=user) | Q(athlete_id__in=granted_athlete_ids)).distinct()


def can_read_workout(user, workout) -> bool:
    """Lecture d'un plan : propriétaire, superutilisateur, ou grant actif.

    Pour un non-propriétaire, l'accès exige que le plan soit rattaché à un
    athlète ET qu'un grant ``sessions:read`` actif et non expiré porte sur ce
    profil (vérifié par ``core.access.can_access_athlete``). Un plan sans
    athlète n'est accessible que par son propriétaire.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or workout.owner_id == user.pk:
        return True
    if workout.athlete_id is None:
        return False
    return access.can_access_athlete(user, workout.athlete, scopes.SESSIONS_READ.name)


def can_write_workout(user, workout) -> bool:
    """Écriture d'un plan (PATCH/PUT/DELETE) : propriétaire ou grant actif.

    Pour un non-propriétaire, l'accès exige que le plan soit rattaché à un
    athlète ET qu'un grant ``sessions:write`` actif et non expiré porte sur ce
    profil. Un grant ``sessions:read`` n'ouvre PAS l'écriture (un scope ne
    déborde jamais sur un autre, cf. ``core.access``).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or workout.owner_id == user.pk:
        return True
    if workout.athlete_id is None:
        return False
    return access.can_access_athlete(user, workout.athlete, scopes.SESSIONS_WRITE.name)
