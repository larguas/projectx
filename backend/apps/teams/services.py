"""Couche de services de la feature 03 (app ``teams``) : logique métier, sans HTTP.

Toutes les mutations de droits passent par ici — c'est le seul endroit où un
``AccessGrant`` ou une ``TeamMembership`` est créé ou modifié, et chaque
mutation émet un événement d'audit (``apps.audit.services.record_event``).

Codes stables levés via ``TeamsServiceError`` (mappés en HTTP par les vues) :
- ``invalid_scope`` / ``invalid_role`` / ``invalid_grantee`` / ``invalid_expiry``
  -> 400 ;
- ``not_found`` -> 404, ``forbidden`` -> 403, ``conflict`` -> 409,
  ``grant_expired`` -> 410.

Décisions documentées :
- un grant à un coach est créé ``pending`` et devient ``active`` à
  l'acceptation par le coach bénéficiaire ;
- un grant à une équipe est créé directement ``active`` (l'équipe est une
  structure choisie explicitement par le sportif) ; l'accès en découle pour
  ses membres actifs ;
- un seul grant non révoqué par ``(athlete, bénéficiaire)`` : pour modifier
  les scopes, révoquer puis recréer (les droits restent révocables à tout
  moment, effet immédiat) ;
- ``granted_at`` est posé à la création du grant.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_event
from apps.teams.models import AccessGrant, Team, TeamMembership
from core import scopes


class TeamsServiceError(Exception):
    """Erreur métier des services teams ; ``code`` est le code stable de l'API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- Équipes et membres ---------------------------------------------------------


def create_team(user, name: str) -> Team:
    """Crée une équipe ; l'utilisateur devient propriétaire (membership actif)."""
    with transaction.atomic():
        team = Team.objects.create(name=name, owner=user)
        TeamMembership.objects.create(
            team=team,
            user=user,
            role=TeamMembership.Role.OWNER,
            status=TeamMembership.Status.ACTIVE,
        )
    record_event(user, "team.created", team)
    return team


def update_team(team, actor, name: str):
    """Renomme une équipe ; seul le propriétaire peut le faire."""
    if team.owner_id != actor.pk:
        raise TeamsServiceError("forbidden", "Seul le propriétaire de l'équipe peut la modifier.")
    team.name = name
    team.save(update_fields=["name", "updated_at"])
    record_event(actor, "team.updated", team)
    return team


def delete_team(team, actor):
    """Supprime une équipe ; seul le propriétaire peut le faire.

    Les memberships et les grants accordés à l'équipe sont supprimés en cascade
    (les droits s'éteignent avec la structure). L'événement d'audit est émis
    AVANT la suppression, pour conserver la référence de la cible.
    """
    if team.owner_id != actor.pk:
        raise TeamsServiceError("forbidden", "Seul le propriétaire de l'équipe peut la supprimer.")
    record_event(actor, "team.deleted", team)
    team.delete()


def get_team_for_user(team_id, user):
    """Équipe si ``user`` en est membre (actif ou en attente) ; sinon ``None``."""
    return (
        Team.objects.filter(
            id=team_id,
            memberships__user=user,
            memberships__status__in=[
                TeamMembership.Status.ACTIVE,
                TeamMembership.Status.PENDING,
            ],
        )
        .distinct()
        .first()
    )


def _get_team_or_404(team_id, user):
    team = get_team_for_user(team_id, user)
    if team is None:
        raise TeamsServiceError("not_found", "Équipe introuvable.")
    return team


def add_member(team, user, actor, role="athlete", request=None):
    """Le propriétaire invite un membre (membership ``pending`` = invitation).

    ``role`` : ``coach`` ou ``athlete`` (le rôle ``owner`` n'est pas assignable) ;
    le propriétaire de l'équipe ne peut pas être réinvité.
    """
    if team.owner_id != actor.pk:
        raise TeamsServiceError(
            "forbidden", "Seul le propriétaire de l'équipe peut ajouter un membre."
        )
    if role not in (TeamMembership.Role.COACH, TeamMembership.Role.ATHLETE):
        raise TeamsServiceError("invalid_role", "Rôle invalide (coach ou athlete attendu).")
    if user.pk == team.owner_id:
        raise TeamsServiceError("conflict", "Le propriétaire est déjà membre de l'équipe.")
    existing = (
        TeamMembership.objects.filter(team=team, user=user)
        .exclude(status=TeamMembership.Status.REMOVED)
        .first()
    )
    if existing is not None:
        raise TeamsServiceError(
            "conflict", "Cet utilisateur a déjà un membership dans cette équipe."
        )
    membership = TeamMembership.objects.create(
        team=team, user=user, role=role, status=TeamMembership.Status.PENDING
    )
    record_event(actor, "team_member.invited", membership, request=request)
    return membership


def accept_member(team, user, request=None):
    """Le membre invité accepte : membership ``pending`` -> ``active``."""
    membership = TeamMembership.objects.filter(team=team, user=user).first()
    if membership is None or membership.status == TeamMembership.Status.REMOVED:
        raise TeamsServiceError("not_found", "Aucune invitation pour cet utilisateur.")
    with transaction.atomic():
        locked = TeamMembership.objects.select_for_update().get(pk=membership.pk)
        if locked.status != TeamMembership.Status.PENDING:
            raise TeamsServiceError("conflict", "Cette invitation a déjà été traitée.")
        locked.status = TeamMembership.Status.ACTIVE
        locked.save(update_fields=["status", "updated_at"])
    record_event(user, "team_member.accepted", locked, request=request)
    return locked


def remove_member(team, user, actor, request=None):
    """Retire un membre (statut ``removed``) : le propriétaire ou le membre lui-même.

    Le propriétaire ne peut pas être retiré (transfert de propriété hors
    périmètre). L'effet est immédiat pour les grants d'équipe : le sélecteur
    central n'autorise que les membres actifs.
    """
    if actor.pk not in (team.owner_id, user.pk):
        raise TeamsServiceError(
            "forbidden", "Seul le propriétaire ou le membre concerné peut retirer un membre."
        )
    if user.pk == team.owner_id:
        raise TeamsServiceError("conflict", "Le propriétaire de l'équipe ne peut pas être retiré.")
    membership = (
        TeamMembership.objects.filter(team=team, user=user)
        .exclude(status=TeamMembership.Status.REMOVED)
        .first()
    )
    if membership is None:
        raise TeamsServiceError("not_found", "Cet utilisateur n'est pas membre de cette équipe.")
    with transaction.atomic():
        locked = TeamMembership.objects.select_for_update().get(pk=membership.pk)
        if locked.status == TeamMembership.Status.REMOVED:
            raise TeamsServiceError("conflict", "Ce membre a déjà été retiré.")
        locked.status = TeamMembership.Status.REMOVED
        locked.save(update_fields=["status", "updated_at"])
    record_event(actor, "team_member.removed", locked, request=request)
    return locked


# --- Autorisations de partage (AccessGrant) ------------------------------------


def _resolve_grantee(grantee_type: str, grantee_id):
    """Résout le bénéficiaire (coach ou équipe) ; ``not_found`` / ``invalid_grantee``."""
    from apps.coaches.models import CoachProfile

    if grantee_type == AccessGrant.GranteeType.COACH:
        coach = CoachProfile.objects.filter(id=grantee_id).first()
        if coach is None:
            raise TeamsServiceError("not_found", "Coach introuvable.")
        return coach
    if grantee_type == AccessGrant.GranteeType.TEAM:
        team = Team.objects.filter(id=grantee_id).first()
        if team is None:
            raise TeamsServiceError("not_found", "Équipe introuvable.")
        return team
    raise TeamsServiceError("invalid_grantee", "Bénéficiaire invalide (coach ou team attendu).")


def grant_access(
    athlete_owner,
    athlete,
    grantee_type: str,
    grantee_id,
    scope_list,
    expires_at=None,
    request=None,
):
    """Crée un grant au nom du propriétaire du profil sportif.

    - seul le propriétaire du profil peut accorder l'accès : un utilisateur ne
      peut PAS créer un grant pour le compte d'un autre sportif ;
    - les scopes sont validés contre ``core.scopes`` (liste non vide, inconnus
      refusés) ;
    - bénéficiaire coach -> statut ``pending`` (acceptation requise) ;
      bénéficiaire équipe -> statut ``active`` immédiat ;
    - un seul grant non révoqué par ``(athlete, bénéficiaire)``.
    """
    if athlete.user_id != athlete_owner.pk:
        raise TeamsServiceError(
            "forbidden", "Seul le propriétaire du profil peut accorder l'accès."
        )
    try:
        clean_scopes = scopes.validate_scopes(scope_list)
    except ValueError as exc:
        raise TeamsServiceError("invalid_scope", str(exc)) from exc
    if expires_at is not None and expires_at <= timezone.now():
        raise TeamsServiceError("invalid_expiry", "La date d'expiration doit être dans le futur.")
    grantee = _resolve_grantee(grantee_type, grantee_id)

    with transaction.atomic():
        base_filter = {"athlete": athlete}
        if grantee_type == AccessGrant.GranteeType.COACH:
            base_filter["grantee_coach"] = grantee
        else:
            base_filter["grantee_team"] = grantee
        existing = (
            AccessGrant.objects.filter(**base_filter)
            .exclude(status=AccessGrant.Status.REVOKED)
            .first()
        )
        if existing is not None:
            raise TeamsServiceError(
                "conflict", "Un grant existe déjà pour ce bénéficiaire (révoquez-le d'abord)."
            )
        status = (
            AccessGrant.Status.PENDING
            if grantee_type == AccessGrant.GranteeType.COACH
            else AccessGrant.Status.ACTIVE
        )
        # ``grantee_type`` est validé par _resolve_grantee : le splat ne peut
        # produire que ``grantee_coach`` ou ``grantee_team``.
        grant = AccessGrant.objects.create(
            athlete=athlete,
            granted_by=athlete_owner,
            grantee_type=grantee_type,
            **{f"grantee_{grantee_type}": grantee},
            scopes=clean_scopes,
            status=status,
            granted_at=timezone.now(),
            expires_at=expires_at,
        )
    record_event(athlete_owner, "access_grant.created", grant, athlete=athlete, request=request)
    return grant


def accept_grant(user, grant_id, request=None):
    """Le coach bénéficiaire accepte un grant ``pending`` -> ``active``.

    Refusé si le grant est expiré (statut basculé en ``expired``, code
    ``grant_expired``) ou déjà traité (``conflict``). La vérification de
    l'email est assurée par la permission ``IsEmailVerified`` côté vue.
    """
    # L'erreur est levée APRÈS la sortie du bloc atomique : ainsi la bascule
    # ``pending -> expired`` (housekeeping) est bien persistée, alors qu'une
    # levée d'exception à l'intérieur aurait tout annulé.
    error: TeamsServiceError | None = None
    with transaction.atomic():
        locked = (
            AccessGrant.objects.select_for_update()
            .filter(
                id=grant_id,
                grantee_type=AccessGrant.GranteeType.COACH,
                grantee_coach__user=user,
            )
            .first()
        )
        if locked is None:
            error = TeamsServiceError("not_found", "Aucun grant à accepter pour cet utilisateur.")
        else:
            now = timezone.now()
            if locked.expires_at is not None and locked.expires_at <= now:
                locked.status = AccessGrant.Status.EXPIRED
                locked.save(update_fields=["status", "updated_at"])
                error = TeamsServiceError("grant_expired", "Ce grant est expiré.")
            elif locked.status != AccessGrant.Status.PENDING:
                error = TeamsServiceError("conflict", "Ce grant a déjà été traité.")
            else:
                locked.status = AccessGrant.Status.ACTIVE
                locked.save(update_fields=["status", "updated_at"])
    if error is not None:
        raise error
    record_event(user, "access_grant.accepted", locked, athlete=locked.athlete, request=request)
    return locked


def revoke_grant(user, grant_id, request=None):
    """Révoque un grant : l'effet est immédiat (le sélecteur exclut les révoqués).

    Seul le propriétaire du profil sportif (``granted_by``) — ou un
    superutilisateur — peut révoquer. Un grant déjà révoqué/ expiré lève
    ``conflict``.
    """
    with transaction.atomic():
        locked = AccessGrant.objects.select_for_update().filter(id=grant_id).first()
        if locked is None:
            raise TeamsServiceError("not_found", "Grant introuvable.")
        if user.pk != locked.granted_by_id and not user.is_superuser:
            raise TeamsServiceError(
                "forbidden", "Seul le propriétaire du profil peut révoquer ce grant."
            )
        if locked.status not in (AccessGrant.Status.PENDING, AccessGrant.Status.ACTIVE):
            raise TeamsServiceError("conflict", "Ce grant ne peut plus être révoqué.")
        locked.status = AccessGrant.Status.REVOKED
        locked.revoked_at = timezone.now()
        locked.save(update_fields=["status", "revoked_at", "updated_at"])
    record_event(user, "access_grant.revoked", locked, athlete=locked.athlete, request=request)
    return locked
