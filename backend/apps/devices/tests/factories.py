"""Factories de test de la feature 04 (app ``devices``).

Usage : ``from apps.devices.tests.factories import DeviceFactory, DeviceModelFactory``.
"""

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.devices.models import Device, DeviceModel


class DeviceModelFactory(DjangoModelFactory):
    """Modèle de capteur du catalogue (valeurs fictives)."""

    class Meta:
        model = DeviceModel

    manufacturer = factory.Sequence(lambda n: f"Fabriquant {n}")
    name = factory.Sequence(lambda n: f"modele_{n}")
    protocol_version = 1
    connection_types = ["ble"]
    capabilities = {
        "emg_channels_max": 8,
        "imu": False,
        "sample_rates": [250, 500],
        "resolution_bits": 16,
    }


class DeviceFactory(DjangoModelFactory):
    """Capteur actif appartenant à un utilisateur de test."""

    class Meta:
        model = Device

    owner = factory.SubFactory(UserFactory)
    device_model = factory.SubFactory(DeviceModelFactory)
    serial_number = factory.Sequence(lambda n: f"SN-{n:06d}")
    name = factory.Sequence(lambda n: f"Capteur {n}")
    firmware_version = "1.0.0"
    status = Device.Status.ACTIVE
