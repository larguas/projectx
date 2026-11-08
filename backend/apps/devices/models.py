"""Modèles de la feature 04 (app ``devices``).

- ``DeviceModel`` : une entrée du catalogue des modèles de capteurs, gérée en
  admin (les utilisateurs n'y ont accès qu'en lecture seule via l'API). Le
  backend ne dépend jamais d'un modèle de capteur particulier (décision
  d'architecture n°4) : tout ce qui caractérise un modèle vit dans ce
  catalogue.
- ``Device`` : un capteur physique appartenant à un utilisateur, identifié par
  ``(device_model, serial_number)``. La suppression via l'API est une
  désactivation logique (``status -> retired``), jamais une suppression
  physique de la ligne.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimestampedModel, UUIDModel


class DeviceModel(TimestampedModel, UUIDModel):
    """Modèle de capteur référencé dans le catalogue (géré en admin).

    ``capabilities`` est un JSON documentant les capacités du matériel ; la
    forme attendue par la plateforme ::

        {
            "emg_channels_max": 8,                    # nombre max de canaux EMG
            "imu": false,                             # capteur IMU embarqué (oui/non)
            "sample_rates": [250, 500, 1000],         # fréquences d'échantillonnage (Hz)
            "resolution_bits": 16                     # résolution des échantillons
        }

    ``connection_types`` est une liste de valeurs de : ``ble``, ``usb``,
    ``serial`` (validée par ``clean()``).
    """

    class ConnectionType(models.TextChoices):
        BLE = "ble", "BLE"
        USB = "usb", "USB"
        SERIAL = "serial", "Série"

    manufacturer = models.CharField("fabriquant", max_length=100)
    name = models.CharField("nom du modèle", max_length=100)
    protocol_version = models.PositiveIntegerField(
        "version de protocole",
        default=1,
        help_text="Version du format de blocs supporté par ce modèle.",
    )
    connection_types = models.JSONField(
        "types de connexion",
        default=list,
        help_text="Sous-ensemble de : ble, usb, serial.",
    )
    capabilities = models.JSONField("capacités", default=dict)

    class Meta:
        verbose_name = "modèle de capteur"
        verbose_name_plural = "modèles de capteurs"
        ordering = ("manufacturer", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("manufacturer", "name"), name="unique_device_model_manufacturer_name"
            )
        ]

    def clean(self) -> None:
        """Valide ``connection_types`` : liste de valeurs connues uniquement."""
        if not isinstance(self.connection_types, list):
            raise ValidationError({"connection_types": "Doit être une liste."})
        allowed = {value for value, _ in self.ConnectionType.choices}
        unknown = [value for value in self.connection_types if value not in allowed]
        if unknown:
            raise ValidationError(
                {
                    "connection_types": (
                        f"Types de connexion inconnus : {', '.join(str(v) for v in unknown)}."
                    )
                }
            )

    def __str__(self) -> str:
        return f"{self.manufacturer} {self.name}"


class Device(TimestampedModel, UUIDModel):
    """Capteur appartenant à un utilisateur.

    L'identité d'un capteur est ``(device_model, serial_number)`` : le même
    numéro de série peut exister sur des modèles différents, mais pas deux
    fois sur un même modèle (contrainte en base). ``DELETE /api/v1/devices/{id}/``
    ne supprime jamais la ligne : elle passe en ``status = retired``.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        RETIRED = "retired", "Retiré"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="propriétaire",
        on_delete=models.CASCADE,
        related_name="devices",
    )
    device_model = models.ForeignKey(
        DeviceModel,
        verbose_name="modèle",
        on_delete=models.PROTECT,
        related_name="devices",
    )
    serial_number = models.CharField("numéro de série", max_length=100)
    name = models.CharField("nom", max_length=200, blank=True)
    firmware_version = models.CharField("version du firmware", max_length=50, blank=True)
    status = models.CharField("statut", max_length=8, choices=Status.choices, default=Status.ACTIVE)
    last_seen_at = models.DateTimeField("dernière connexion", null=True, blank=True)
    calibration_defaults = models.JSONField("défauts de calibration", default=dict, blank=True)

    class Meta:
        verbose_name = "capteur"
        verbose_name_plural = "capteurs"
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("device_model", "serial_number"), name="unique_serial_per_device_model"
            )
        ]

    def __str__(self) -> str:
        return f"{self.device_model} n°{self.serial_number}"
