"""Modèles de la feature 03 (app ``audit``).

``AuditEvent`` : trace en insertion seule des mutations de droits (grants,
membres d'équipe) et des lectures de données d'un sportif par un coach.
Consultation, export et politique de rétention : feature 14 (hors périmètre).

L'insertion seule est garantie au niveau du modèle (``save`` / ``delete``
refusés après persistance) ; le modèle ne porte volontairement aucun champ
modifiable (pas de ``updated_at``).
"""

from django.conf import settings
from django.db import models

from core.models import UUIDModel


class AuditError(RuntimeError):
    """Tentative de modification ou de suppression d'un événement d'audit."""


class AuditEvent(UUIDModel):
    """Événement d'audit immuable (insertion seule)."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="acteur",
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    action = models.CharField("action", max_length=100)
    target_type = models.CharField("type de cible", max_length=100, blank=True, default="")
    target_id = models.UUIDField("identifiant de la cible", null=True, blank=True)
    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        verbose_name="sportif concerné",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    ip = models.GenericIPAddressField("adresse IP", null=True, blank=True)
    user_agent = models.CharField("user agent", max_length=512, blank=True, default="")
    metadata = models.JSONField("métadonnées", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "événement d'audit"
        verbose_name_plural = "événements d'audit"
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditError("Les événements d'audit sont en insertion seule.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # noqa: ARG002 - signature Django
        raise AuditError("Les événements d'audit ne peuvent pas être supprimés.")

    def __str__(self) -> str:
        return f"{self.action} par {self.actor}"
