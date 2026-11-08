"""Modèles de base abstraits partagés par toutes les apps.

Conventions (voir AGENT.md) : clés primaires UUID, horodatages systématiques.
"""

import uuid

from django.db import models


class UUIDModel(models.Model):
    """Modèle abstrait avec clé primaire UUID."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimestampedModel(models.Model):
    """Modèle abstrait avec ``created_at`` / ``updated_at``."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
