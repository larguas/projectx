"""Modèles de la feature 03 (app ``coaches``).

``CoachProfile`` : le profil coach rattaché à un utilisateur. Un utilisateur
peut cumuler les rôles sportif et coach (un profil par rôle) ; il devient
coach en créant ce profil, sans nouveau compte. Un coach ne voit les données
d'un sportif que si celui-ci lui a accordé un ``AccessGrant`` actif portant le
scope correspondant (voir ``core.access``).
"""

from django.conf import settings
from django.db import models

from core.models import TimestampedModel, UUIDModel


class CoachProfile(TimestampedModel, UUIDModel):
    """Profil coach : identité professionnelle d'un utilisateur."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="utilisateur",
        on_delete=models.CASCADE,
        related_name="coach_profile",
    )
    organization_name = models.CharField("structure / organisation", max_length=200, blank=True)
    bio = models.TextField("bio", blank=True)

    class Meta:
        verbose_name = "profil coach"
        verbose_name_plural = "profils coach"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"Profil coach de {self.user.email}"
