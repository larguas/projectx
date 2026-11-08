"""Tests de l'API capteur : ``GET/PATCH/DELETE /api/v1/devices/{id}/``.

Le détail est visible selon ``apps.devices.selectors.can_read_device`` (404 sinon,
l'existence n'est pas révélée) ; la mise à jour et la désactivation logique sont
réservées au propriétaire (403 sinon). Le DELETE ne supprime jamais la ligne
(``status -> retired``, auditée) ; PUT est refusé (405, périmètre API).
"""

import json
from datetime import timedelta

from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.devices.models import Device
from apps.devices.tests.factories import DeviceFactory, DeviceModelFactory
from apps.teams.models import AccessGrant
from apps.teams.tests.factories import AccessGrantFactory

SCOPE = "devices:read"


def patch_json(client, url: str, payload: dict, **extra):
    """PATCH JSON via le client de test Django (``**extra`` : en-têtes HTTP)."""
    return client.patch(url, data=json.dumps(payload), content_type="application/json", **extra)


class TestDeviceDetailRead:
    def test_anonymous_refused(self, client):
        device = DeviceFactory()
        response = client.get(f"/api/v1/devices/{device.pk}/")
        assert response.status_code == 401

    def test_owner_sees_own_device_with_email(self, client):
        owner = UserFactory(email="sportif@example.com")
        device = DeviceFactory(owner=owner)
        response = client.get(f"/api/v1/devices/{device.pk}/", **auth_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["owner_email"] == "sportif@example.com"

    def test_coach_with_grant_sees_device_without_email(self, client):
        """Un coach autorisé ne reçoit pas l'email du propriétaire (donnée privée)."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory(user=UserFactory(email="secret@example.com"))
        device = DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE])
        response = client.get(f"/api/v1/devices/{device.pk}/", **auth_headers(coach_user))
        assert response.status_code == 200
        assert response.json()["owner_email"] is None

    def test_coach_without_grant_gets_404(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        device = DeviceFactory()
        response = client.get(f"/api/v1/devices/{device.pk}/", **auth_headers(coach_user))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_grant_without_devices_read_scope_gets_404(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        device = DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=["sessions:read"])
        response = client.get(f"/api/v1/devices/{device.pk}/", **auth_headers(coach_user))
        assert response.status_code == 404

    def test_revoked_grant_gets_404(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        device = DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(
            athlete=athlete_profile, grantee_coach=coach, status=AccessGrant.Status.REVOKED
        )
        response = client.get(f"/api/v1/devices/{device.pk}/", **auth_headers(coach_user))
        assert response.status_code == 404

    def test_expired_grant_gets_404(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        device = DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(
            athlete=athlete_profile,
            grantee_coach=coach,
            expires_at=timezone.now() - timedelta(days=1),
        )
        response = client.get(f"/api/v1/devices/{device.pk}/", **auth_headers(coach_user))
        assert response.status_code == 404

    def test_stranger_gets_404(self, client):
        device = DeviceFactory()
        stranger = UserFactory()
        response = client.get(f"/api/v1/devices/{device.pk}/", **auth_headers(stranger))
        assert response.status_code == 404

    def test_owner_without_athlete_profile_not_accessible_by_coach(self, client):
        """Un propriétaire sans profil sportif n'est accessible que par lui-même."""
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        device = DeviceFactory()  # owner sans AthleteProfile
        response = client.get(f"/api/v1/devices/{device.pk}/", **auth_headers(coach_user))
        assert response.status_code == 404

    def test_unknown_id_gets_404(self, client):
        user = UserFactory()
        response = client.get(
            "/api/v1/devices/00000000-0000-4000-8000-000000000000/", **auth_headers(user)
        )
        assert response.status_code == 404

    def test_coach_read_emits_audit_event(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        device = DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE])
        client.get(f"/api/v1/devices/{device.pk}/", **auth_headers(coach_user))
        event = AuditEvent.objects.get(action="device.viewed")
        assert event.actor_id == coach_user.pk
        assert event.target_id == device.pk
        assert event.athlete_id == athlete_profile.pk

    def test_owner_read_no_audit_event(self, client):
        owner = UserFactory()
        device = DeviceFactory(owner=owner)
        client.get(f"/api/v1/devices/{device.pk}/", **auth_headers(owner))
        assert not AuditEvent.objects.filter(action="device.viewed").exists()


class TestDeviceDetailUpdate:
    def test_owner_updates_own_device(self, client):
        owner = UserFactory()
        device = DeviceFactory(owner=owner)
        response = patch_json(
            client,
            f"/api/v1/devices/{device.pk}/",
            {
                "name": "Capteur main gauche",
                "firmware_version": "2.0.0",
                "calibration_defaults": {"offsets": [0, 1]},
            },
            **auth_headers(owner),
        )
        assert response.status_code == 200, response.data
        device.refresh_from_db()
        assert device.name == "Capteur main gauche"
        assert device.firmware_version == "2.0.0"
        assert device.calibration_defaults == {"offsets": [0, 1]}

    def test_identity_fields_not_updatable(self, client):
        """``device_model`` / ``serial_number`` / ``status`` forment l'identité : ignorés en PATCH."""
        owner = UserFactory()
        device = DeviceFactory(owner=owner)
        other_model = DeviceModelFactory()
        response = patch_json(
            client,
            f"/api/v1/devices/{device.pk}/",
            {
                "serial_number": "SN-NEW",
                "device_model": str(other_model.pk),
                "status": "retired",
            },
            **auth_headers(owner),
        )
        assert response.status_code == 200, response.data
        device.refresh_from_db()
        assert device.serial_number != "SN-NEW"
        assert device.device_model_id != other_model.pk
        assert device.status == Device.Status.ACTIVE

    def test_coach_cannot_update(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        device = DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE])
        response = patch_json(
            client, f"/api/v1/devices/{device.pk}/", {"name": "Hacked"}, **auth_headers(coach_user)
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_stranger_cannot_update(self, client):
        device = DeviceFactory()
        stranger = UserFactory()
        response = patch_json(
            client, f"/api/v1/devices/{device.pk}/", {"name": "X"}, **auth_headers(stranger)
        )
        assert response.status_code == 404

    def test_anonymous_cannot_update(self, client):
        device = DeviceFactory()
        response = patch_json(client, f"/api/v1/devices/{device.pk}/", {"name": "X"})
        assert response.status_code == 401

    def test_put_refused(self, client):
        """Le périmètre API est GET/PATCH/DELETE : PUT renvoie 405."""
        owner = UserFactory()
        device = DeviceFactory(owner=owner)
        response = client.put(
            f"/api/v1/devices/{device.pk}/",
            data=json.dumps({"name": "X"}),
            content_type="application/json",
            **auth_headers(owner),
        )
        assert response.status_code == 405


class TestDeviceDetailDestroy:
    def test_owner_retires_own_device_logically(self, client):
        owner = UserFactory()
        device = DeviceFactory(owner=owner)
        response = client.delete(f"/api/v1/devices/{device.pk}/", **auth_headers(owner))
        assert response.status_code == 204
        # Jamais de suppression physique : la ligne persiste, désactivée.
        assert Device.objects.filter(pk=device.pk).exists()
        device.refresh_from_db()
        assert device.status == Device.Status.RETIRED

    def test_retired_device_still_listed_with_status(self, client):
        owner = UserFactory()
        device = DeviceFactory(owner=owner)
        client.delete(f"/api/v1/devices/{device.pk}/", **auth_headers(owner))
        listing = client.get("/api/v1/devices/", **auth_headers(owner)).json()["results"]
        assert [d["id"] for d in listing] == [str(device.pk)]
        assert listing[0]["status"] == "retired"

    def test_retire_emits_audit_event(self, client):
        owner = UserFactory()
        athlete_profile = AthleteProfileFactory(user=owner)
        device = DeviceFactory(owner=owner)
        client.delete(f"/api/v1/devices/{device.pk}/", **auth_headers(owner))
        event = AuditEvent.objects.get(action="device.retired")
        assert event.actor_id == owner.pk
        assert event.target_id == device.pk
        assert event.athlete_id == athlete_profile.pk

    def test_coach_cannot_retire(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        device = DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE])
        response = client.delete(f"/api/v1/devices/{device.pk}/", **auth_headers(coach_user))
        assert response.status_code == 403
        device.refresh_from_db()
        assert device.status == Device.Status.ACTIVE

    def test_stranger_cannot_retire(self, client):
        device = DeviceFactory()
        stranger = UserFactory()
        response = client.delete(f"/api/v1/devices/{device.pk}/", **auth_headers(stranger))
        assert response.status_code == 404

    def test_anonymous_cannot_retire(self, client):
        device = DeviceFactory()
        response = client.delete(f"/api/v1/devices/{device.pk}/")
        assert response.status_code == 401
