"""Tests de la couche services (``apps.devices.services``).

Couvre les règles métier hors HTTP : création avec contrôle du doublon de
serial, mise à jour / retrait réservés au propriétaire, ``touch_device``
(point d'entrée de l'ingestion, feature 07).
"""

from datetime import UTC

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.devices.models import Device
from apps.devices.services import (
    DevicesServiceError,
    create_device,
    retire_device,
    touch_device,
    update_device,
)
from apps.devices.tests.factories import DeviceFactory, DeviceModelFactory


class TestCreateDevice:
    def test_creates_device_owned_by_user(self):
        owner = UserFactory()
        model = DeviceModelFactory()
        device = create_device(owner, {"device_model": model, "serial_number": "SN-1"})
        assert device.owner_id == owner.pk
        assert device.status == Device.Status.ACTIVE

    def test_duplicate_serial_same_model_raises_conflict(self):
        owner = UserFactory()
        model = DeviceModelFactory()
        data = {"device_model": model, "serial_number": "SN-DUP"}
        create_device(owner, data)
        with pytest.raises(DevicesServiceError) as excinfo:
            create_device(owner, data)
        assert excinfo.value.code == "conflict"
        assert "SN-DUP" in excinfo.value.message

    def test_same_serial_different_model_allowed(self):
        owner = UserFactory()
        model_a = DeviceModelFactory()
        model_b = DeviceModelFactory()
        device_a = create_device(owner, {"device_model": model_a, "serial_number": "SN-X"})
        device_b = create_device(owner, {"device_model": model_b, "serial_number": "SN-X"})
        assert device_a.pk != device_b.pk


class TestUpdateDevice:
    def test_owner_updates(self):
        owner = UserFactory()
        device = DeviceFactory(owner=owner)
        updated = update_device(owner, device, {"name": "Nouveau nom"})
        assert updated.name == "Nouveau nom"

    def test_non_owner_forbidden(self):
        device = DeviceFactory()
        stranger = UserFactory()
        with pytest.raises(DevicesServiceError) as excinfo:
            update_device(stranger, device, {"name": "X"})
        assert excinfo.value.code == "forbidden"


class TestRetireDevice:
    def test_owner_retires(self):
        owner = UserFactory()
        device = DeviceFactory(owner=owner)
        retired = retire_device(owner, device)
        assert retired.status == Device.Status.RETIRED
        # Désactivation logique : la ligne persiste.
        assert Device.objects.filter(pk=device.pk).exists()

    def test_non_owner_forbidden(self):
        device = DeviceFactory()
        stranger = UserFactory()
        with pytest.raises(DevicesServiceError) as excinfo:
            retire_device(stranger, device)
        assert excinfo.value.code == "forbidden"


class TestTouchDevice:
    def test_updates_last_seen_at_with_explicit_time(self):
        from datetime import datetime

        device = DeviceFactory(last_seen_at=None)
        at = datetime(2026, 1, 1, tzinfo=UTC)
        touched = touch_device(device, at=at)
        assert touched.last_seen_at == at

    def test_defaults_to_now(self):
        from django.utils import timezone

        device = DeviceFactory(last_seen_at=None)
        before = timezone.now()
        touched = touch_device(device)
        after = timezone.now()
        assert before <= touched.last_seen_at <= after
