"""Module d'accès central de la plateforme (décision d'architecture n°8).

SEUL point d'entrée des contrôles d'autorisation sur les données d'un sportif.
Toutes les apps (sessions, analytics, reports, devices, setups…) doivent passer
par ``can_access_athlete`` / ``visible_athletes`` : jamais de requête directe
sur les grants dans une vue ou un sélecteur métier.

Règles implémentées (deny by default) :
- un utilisateur non authentifié n'a aucun accès ;
- le propriétaire d'un profil sportif accède à ses propres données, tous
  scopes confondus ;
- un superutilisateur Django a un accès total (usage opérationnel/administratif,
  décision documentée de la feature 03) ;
- sinon, l'accès exige un ``AccessGrant`` dont :
  - le statut est ``active`` ET la date d'expiration non dépassée
    (un grant révoqué ou expiré n'ouvre AUCUN accès — vérifié ici, au niveau
    du sélecteur, et non seulement dans les vues) ;
  - le bénéficiaire est l'utilisateur : coach (``grantee_coach__user``) ou
    membre ACTIF d'une équipe (``grantee_team`` + membership ``active``) ;
  - la liste ``scopes`` contient le scope demandé (un grant
    ``sessions:read`` n'ouvre pas ``reports:read``) ;
- un scope inconnu est refusé (deny by default, cf. ``core.scopes``).

Exemple::

    from core import access

    # Dans une vue / service d'une autre app :
    if not access.can_access_athlete(request.user, athlete, "sessions:read"):
        raise PermissionDenied()

    athletes = access.visible_athletes(request.user, "analytics:read")
"""

from __future__ import annotations

from datetime import datetime

from django.db.models import Q
from django.db.models.query import QuerySet
from django.utils import timezone

from core import scopes


def _now() -> datetime:
    return timezone.now()


def _active_grants_for(user) -> QuerySet:
    """Grants ouvrant un accès pour ``user`` : statut actif et non expirés.

    Un grant est « ouvert » si son statut est ``active`` ET que ``expires_at``
    est vide ou futur. Les statuts ``pending`` / ``revoked`` / ``expired`` et
    les dates dépassées sont exclus ICI (niveau sélecteur), indépendamment des
    vues : c'est le point de contrôle unique.
    """
    from apps.teams.models import AccessGrant, TeamMembership

    return (
        AccessGrant.objects.filter(
            status=AccessGrant.Status.ACTIVE,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=_now()))
        .filter(
            Q(grantee_type=AccessGrant.GranteeType.COACH, grantee_coach__user=user)
            | Q(
                grantee_type=AccessGrant.GranteeType.TEAM,
                grantee_team__memberships__user=user,
                grantee_team__memberships__status=TeamMembership.Status.ACTIVE,
            )
        )
        .distinct()
    )


def _has_access(user, athlete) -> bool:
    """L'utilisateur est-il le propriétaire du profil ou un superutilisateur ?"""
    if user.is_superuser:
        return True
    return athlete.user_id == user.pk


def can_see_athlete(user, athlete) -> bool:
    """Le profil (métadonnées de base) d'``athlete`` est-il visible par ``user`` ?

    Niveau « profil », sans scope : propriétaire, superutilisateur, ou au moins
    un grant actif (quel que soit le scope). À utiliser pour le détail d'un
    profil ; l'accès aux données métier reste gouverné par
    ``can_access_athlete(user, athlete, scope)``.

    Exemple::

        if not access.can_see_athlete(request.user, profile):
            raise NotFound()  # 404 : ne pas révéler l'existence du profil
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _has_access(user, athlete):
        return True
    return _active_grants_for(user).filter(athlete=athlete).exists()


def granted_athletes(user) -> QuerySet:
    """Profils sportifs couverts par au moins un grant actif (tout scope confondu).

    Base de la liste ``GET /api/v1/athletes/`` côté coach/équipe : propriétaire
    + sportifs avec un ou plusieurs grants actifs. Pour filtrer par scope,
    préférer ``visible_athletes(user, scope)``.
    """
    from apps.athletes.models import AthleteProfile

    qs = AthleteProfile.objects.all()
    if user is None or not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser:
        return qs
    granted_ids = _active_grants_for(user).values_list("athlete_id", flat=True)
    return qs.filter(Q(user=user) | Q(id__in=granted_ids)).distinct()


def can_access_athlete(user, athlete, scope: str) -> bool:
    """Vrai si ``user`` peut accéder aux données d'``athlete`` pour ``scope``.

    Args:
        user: utilisateur authentifié (ou ``AnonymousUser`` / ``None``).
        athlete: instance ``AthleteProfile`` ciblée.
        scope: nom de scope enregistré dans ``core.scopes``.

    Returns:
        ``True`` uniquement si un accès est ouvert (propriétaire, superuser ou
        grant actif portant ce scope) ; sinon ``False`` — y compris pour un
        scope inconnu.

    Exemple::

        access.can_access_athlete(coach, athlete, "sessions:read")  # True
        access.can_access_athlete(coach, athlete, "reports:read")   # False
        (grant actif limité à ``sessions:read``)
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not scopes.is_known_scope(scope):
        return False
    if _has_access(user, athlete):
        return True
    return _active_grants_for(user).filter(athlete=athlete, scopes__contains=[scope]).exists()


def visible_athletes(user, scope: str) -> QuerySet:
    """Profils sportifs visibles par ``user`` pour ``scope`` (sélecteur de liste).

    Retourne un ``QuerySet[AthleteProfile]`` filtré : propriétaire + sportifs
    couverts par un grant actif portant le scope. À utiliser comme base des
    listes côté coach/équipe — aucune liste ne doit exposer un sportif non
    autorisé.

    Args:
        user: utilisateur authentifié (ou ``AnonymousUser`` / ``None``).
        scope: nom de scope enregistré dans ``core.scopes``.

    Returns:
        ``QuerySet`` vide pour un utilisateur non authentifié ou un scope
        inconnu ; tous les profils pour un superutilisateur.

    Exemple::

        athletes = access.visible_athletes(request.user, "analytics:read")
        serializer = AthleteSerializer(athletes, many=True)
    """
    from apps.athletes.models import AthleteProfile

    qs = AthleteProfile.objects.all()
    if user is None or not getattr(user, "is_authenticated", False):
        return qs.none()
    if not scopes.is_known_scope(scope):
        return qs.none()
    if user.is_superuser:
        return qs
    granted_ids = (
        _active_grants_for(user)
        .filter(scopes__contains=[scope])
        .values_list("athlete_id", flat=True)
    )
    return qs.filter(Q(user=user) | Q(id__in=granted_ids)).distinct()
