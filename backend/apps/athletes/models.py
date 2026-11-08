"""Modèles de la feature 03 (app ``athletes``).

``AthleteProfile`` : le profil sportif rattaché à un utilisateur. Un
utilisateur individuel autonome peut créer ce profil sans coach ni équipe ;
il n'est PAS créé à l'inscription, mais à la demande (endpoint dédié,
feature 03). Les données d'un sportif restent privées par défaut : un coach
ou une équipe n'y accède que via un ``AccessGrant`` actif (voir
``core.access``).
"""

from django.conf import settings
from django.db import models

from core.models import TimestampedModel, UUIDModel


class AthleteProfile(TimestampedModel, UUIDModel):
    """Profil sportif : données de base d'un utilisateur suivi sur la plateforme."""

    class Sex(models.TextChoices):
        FEMALE = "female", "Femme"
        MALE = "male", "Homme"
        NON_BINARY = "non_binary", "Non binaire"

    class DominantSide(models.TextChoices):
        LEFT = "left", "Gauche"
        RIGHT = "right", "Droite"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="utilisateur",
        on_delete=models.CASCADE,
        related_name="athlete_profile",
    )
    date_of_birth = models.DateField("date de naissance")
    sex = models.CharField("sexe", max_length=16, choices=Sex.choices, blank=True)
    height_cm = models.PositiveIntegerField("taille (cm)", null=True, blank=True)
    weight_kg = models.PositiveIntegerField("poids (kg)", null=True, blank=True)
    dominant_side = models.CharField(
        "côté dominant", max_length=8, choices=DominantSide.choices, blank=True
    )
    sport = models.CharField("sport principal", max_length=100, blank=True)
    notes = models.TextField("notes", blank=True)

    class Meta:
        verbose_name = "profil sportif"
        verbose_name_plural = "profils sportifs"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"Profil sportif de {self.user.email}"
