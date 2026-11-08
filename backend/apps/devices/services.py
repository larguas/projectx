"""Couche de services de la feature 04 (app ``devices``).

Règles :
- un capteur appartient à son propriétaire ; seul celui-ci peut le créer, le
  modifier ou le retirer (un grant ``devices:read`` n'autorise que la lecture) ;
- ``DELETE /api/v1/devices/{id}/`` = désactivation logique (``status ->
  retired``) : aucune suppression physique de capteur par l'API, pour garder
  l'historique des données ingérées traçable ;
- le doublon de ``(device_model, serial_number)`` est contrôlé ici avec un
  message clair (code stable ``conflict``) ; la contrainte en base reste le
  filet de sécurité (IntegrityError -> 409 générique).

Les erreurs lèvent ``DevicesServiceError`` avec un code stable mappé en HTTP
par les vues (``conflict`` -> 409, ``forbidden`` -> 403).

Aucune logique ne dépend d'un modèle de capteur particulier (décision
d'architecture n°4) : le code ne référence jamais un modèle spécifique.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from apps.devices.models import Device


class DevicesServiceError(Exception):
    """Erreur métier des services devices ; ``code`` est le code stable de l'API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def create_device(user, data: dict) -> Device:
    """Crée un capteur pour ``user`` ; ``conflict`` si le serial est déjà pris.

    ``data`` contient les champs validés par le sérialiseur de création
    (``device_model``, ``serial_number``, …).
    """
    from apps.devices.models import Device

    model = data["device_model"]
    if Device.objects.filter(device_model=model, serial_number=data["serial_number"]).exists():
        raise DevicesServiceError(
            "conflict",
            f"Un capteur du modèle « {model} » porte déjà le numéro de série "
            f"« {data['serial_number']} ».",
        )
    return Device.objects.create(owner=user, **data)


def update_device(user, device: Device, data: dict) -> Device:
    """Met à jour un capteur ; seul le propriétaire peut le faire."""
    if device.owner_id != user.pk:
        raise DevicesServiceError("forbidden", "Seul le propriétaire peut modifier ce capteur.")
    for field, value in data.items():
        setattr(device, field, value)
    device.save()
    return device


def retire_device(user, device: Device) -> Device:
    """Désactive logiquement un capteur (``status -> retired``).

    Jamais de suppression physique : l'historique des données ingérées reste
    traçable. Seul le propriétaire peut retirer son capteur.
    """
    from apps.devices.models import Device

    if device.owner_id != user.pk:
        raise DevicesServiceError("forbidden", "Seul le propriétaire peut retirer ce capteur.")
    device.status = Device.Status.RETIRED
    device.save(update_fields=["status", "updated_at"])
    return device


def touch_device(device: Device, at: datetime | None = None) -> Device:
    """Met à jour ``last_seen_at`` d'un capteur.

    Point d'entrée de la couche ingestion (feature 07) : appelé à chaque bloc
    reçu pour marquer le capteur comme vu. Ne dépend d'aucun modèle de
    capteur (décision n°4).
    """
    device.last_seen_at = at or timezone.now()
    device.save(update_fields=["last_seen_at"])
    return device
