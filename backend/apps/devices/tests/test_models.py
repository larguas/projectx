"""Tests des modèles (contraintes de base et validation).

Note : la base de tests contient déjà le modèle seedé ``EMG prototype_v1``
(migration de données) — les tests d'unicité utilisent donc d'autres valeurs.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.devices.models import Device, DeviceModel
from apps.devices.tests.factories import DeviceFactory, DeviceModelFactory


class TestDeviceModel:
    def test_unique_manufacturer_name(self):
        DeviceModelFactory(manufacturer="TestFab", name="modele-x")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                DeviceModel.objects.create(manufacturer="TestFab", name="modele-x")

    def test_clean_rejects_unknown_connection_type(self):
        model = DeviceModelFactory(connection_types=["ble", "colibri"])
        with pytest.raises(ValidationError) as excinfo:
            model.full_clean()
        assert "connection_types" in excinfo.value.message_dict

    def test_clean_rejects_non_list_connection_types(self):
        model = DeviceModelFactory(connection_types="ble")
        with pytest.raises(ValidationError):
            model.full_clean()

    def test_clean_accepts_known_types(self):
        model = DeviceModelFactory(connection_types=["ble", "usb", "serial"])
        model.full_clean()  # ne lève pas


class TestDevice:
    def test_unique_serial_per_model(self):
        device = DeviceFactory(serial_number="SN-1")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Device.objects.create(
                    owner=device.owner,
                    device_model=device.device_model,
                    serial_number="SN-1",
                )

    def test_same_serial_allowed_on_other_model(self):
        device = DeviceFactory(serial_number="SN-SHARED")
        other_model = DeviceModelFactory()
        created = Device.objects.create(
            owner=device.owner, device_model=other_model, serial_number="SN-SHARED"
        )
        assert created.pk != device.pk

    def test_device_model_protected_when_devices_exist(self):
        """Le catalogue ne peut pas retirer un modèle encore référencé par un capteur."""
        device = DeviceFactory()
        with pytest.raises(ProtectedError):
            device.device_model.delete()

    def test_default_status_active(self):
        device = DeviceFactory()
        assert device.status == Device.Status.ACTIVE
