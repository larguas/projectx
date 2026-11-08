"""Modèles de la feature 03 (app ``teams``).

- ``Team`` : une équipe / structure, avec un propriétaire.
- ``TeamMembership`` : l'appartenance à une équipe (rôle + statut).
- ``AccessGrant`` : l'autorisation explicite, à scopes et révocable de partage
  des données d'un sportif (décision d'architecture n°8).

Décision documentée ici : ``AccessGrant`` vit dans l'app ``teams`` (plutôt que
dans une app ``sharing`` dédiée) car ses bénéficiaires sont les acteurs de
cette app (coach / équipe). Le module d'accès central reste dans
``core.access`` et est réutilisable par toutes les apps.

Règles :
- un grant n'ouvre l'accès que s'il est ``active`` ET non expiré ; cet
  invariant est vérifié au niveau des sélecteurs (``core.access``), pas
  seulement dans les vues ;
- exactement un seul de ``grantee_coach`` / ``grantee_team`` est rempli et doit
  correspondre à ``grantee_type`` (``CheckConstraint`` en base) ;
- une invitation est un grant ou un membership ``pending`` (statut simple en
  base pour l'instant, pas de notification — hors périmètre).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimestampedModel, UUIDModel


class Team(TimestampedModel, UUIDModel):
    """Équipe / structure : regroupement d'utilisateurs (club, organisation)."""

    name = models.CharField("nom", max_length=200)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="propriétaire",
        on_delete=models.PROTECT,
        related_name="owned_teams",
    )

    class Meta:
        verbose_name = "équipe"
        verbose_name_plural = "équipes"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.name


class TeamMembership(TimestampedModel, UUIDModel):
    """Appartenance d'un utilisateur à une équipe.

    Un seul membership non retiré par ``(team, user)`` (contrainte partielle) :
    un membre retiré peut être réinvité sans dupliquer l'historique.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Propriétaire"
        COACH = "coach", "Coach"
        ATHLETE = "athlete", "Sportif"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACTIVE = "active", "Actif"
        REMOVED = "removed", "Retiré"

    team = models.ForeignKey(
        Team, verbose_name="équipe", on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="membre",
        on_delete=models.CASCADE,
        related_name="team_memberships",
    )
    role = models.CharField("rôle", max_length=20, choices=Role.choices, default=Role.ATHLETE)
    status = models.CharField(
        "statut", max_length=20, choices=Status.choices, default=Status.PENDING
    )

    class Meta:
        verbose_name = "appartenance à une équipe"
        verbose_name_plural = "appartenances à des équipes"
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("team", "user"),
                condition=~models.Q(status="removed"),
                name="unique_membership_per_team_user",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.team} ({self.role})"


class AccessGrant(TimestampedModel, UUIDModel):
    """Autorisation explicite de partage des données d'un sportif.

    Créée par le sportif (``granted_by``) au profit d'un coach ou d'une équipe
    (``grantee_*``, un seul rempli), avec une liste de scopes validés par
    ``core.scopes``. Révocable à tout moment ; un grant ``revoked`` ou expiré
    n'ouvre aucun accès (vérifié dans ``core.access``).
    """

    class GranteeType(models.TextChoices):
        COACH = "coach", "Coach"
        TEAM = "team", "Équipe"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente d'acceptation"
        ACTIVE = "active", "Actif"
        REVOKED = "revoked", "Révoqué"
        EXPIRED = "expired", "Expiré"

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        verbose_name="sportif",
        on_delete=models.CASCADE,
        related_name="access_grants",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="accordé par",
        on_delete=models.PROTECT,
        related_name="granted_accesses",
    )
    grantee_type = models.CharField(
        "type de bénéficiaire", max_length=10, choices=GranteeType.choices
    )
    grantee_coach = models.ForeignKey(
        "coaches.CoachProfile",
        verbose_name="coach bénéficiaire",
        on_delete=models.CASCADE,
        related_name="access_grants",
        null=True,
        blank=True,
    )
    grantee_team = models.ForeignKey(
        Team,
        verbose_name="équipe bénéficiaire",
        on_delete=models.CASCADE,
        related_name="access_grants",
        null=True,
        blank=True,
    )
    scopes = models.JSONField("scopes", default=list)
    status = models.CharField(
        "statut", max_length=20, choices=Status.choices, default=Status.PENDING
    )
    granted_at = models.DateTimeField("accordé le", null=True, blank=True)
    revoked_at = models.DateTimeField("révoqué le", null=True, blank=True)
    expires_at = models.DateTimeField("expiration", null=True, blank=True)

    class Meta:
        verbose_name = "autorisation de partage"
        verbose_name_plural = "autorisations de partage"
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(grantee_type="coach")
                        & models.Q(grantee_coach_id__isnull=False)
                        & models.Q(grantee_team_id__isnull=True)
                    )
                    | (
                        models.Q(grantee_type="team")
                        & models.Q(grantee_coach_id__isnull=True)
                        & models.Q(grantee_team_id__isnull=False)
                    )
                ),
                name="grantee_xor_matches_type",
            )
        ]

    def is_active(self) -> bool:
        """Vrai si le grant ouvre l'accès : statut ``active`` et non expiré."""
        if self.status != self.Status.ACTIVE:
            return False
        return self.expires_at is None or timezone.now() < self.expires_at

    def __str__(self) -> str:
        grantee = self.grantee_coach or self.grantee_team
        return f"{self.athlete.user} -> {grantee}"
