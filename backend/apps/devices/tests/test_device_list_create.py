"""Tests de l'API capteurs : ``GET/POST /api/v1/devices/``.

La liste est filtrée par le sélecteur (``apps.devices.selectors.visible_devices``) :
un utilisateur y voit ses capteurs + ceux de ses sportifs couverts par un grant
actif (non expiré) portant le scope ``devices:read``. La création porte sur
l'utilisateur connecté ; le doublon ``(device_model, serial_number)`` est refusé
avec un 409 et un message clair (code stable ``conflict``).
"""

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.devices.models import Device, DeviceModel
from apps.devices.tests.factories import DeviceFactory, DeviceModelFactory
from apps.teams.models import AccessGrant
from apps.teams.tests.factories import (
    AccessGrantFactory,
    TeamAccessGrantFactory,
    TeamFactory,
    TeamMembershipFactory,
)

SCOPE = "devices:read"


def _prototype_v1() -> DeviceModel:
    """Le modèle seedé par la migration de données (``EMG prototype_v1``)."""
    return DeviceModel.objects.get(manufacturer="EMG", name="prototype_v1")


class TestDeviceList:
    def test_anonymous_refused(self, client):
        response = client.get("/api/v1/devices/")
        assert response.status_code == 401

    def test_owner_sees_own_devices_only(self, client):
        owner = UserFactory()
        model = DeviceModelFactory()
        own_a = DeviceFactory(owner=owner, device_model=model)
        own_b = DeviceFactory(owner=owner, device_model=model)
        DeviceFactory()  # capteur d'un tiers : invisible pour l'owner
        response = client.get("/api/v1/devices/", **auth_headers(owner))
        assert response.status_code == 200
        results = response.json()["results"]
        assert {d["id"] for d in results} == {str(own_a.pk), str(own_b.pk)}

    def test_coach_sees_only_devices_with_devices_read_grant(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        granted_device = DeviceFactory(owner=athlete_profile.user)
        DeviceFactory()  # capteur d'un sportif sans grant : invisible pour le coach
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE])
        response = client.get("/api/v1/devices/", **auth_headers(coach_user))
        assert response.status_code == 200
        assert [d["id"] for d in response.json()["results"]] == [str(granted_device.pk)]

    def test_grant_without_devices_read_scope_excluded(self, client):
        """Un grant ``sessions:read`` n'ouvre pas la lecture des capteurs."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=["sessions:read"])
        response = client.get("/api/v1/devices/", **auth_headers(coach_user))
        assert response.json()["results"] == []

    def test_revoked_grant_excluded(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(
            athlete=athlete_profile, grantee_coach=coach, status=AccessGrant.Status.REVOKED
        )
        response = client.get("/api/v1/devices/", **auth_headers(coach_user))
        assert response.json()["results"] == []

    def test_expired_grant_excluded(self, client):
        from django.utils import timezone

        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(
            athlete=athlete_profile,
            grantee_coach=coach,
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        response = client.get("/api/v1/devices/", **auth_headers(coach_user))
        assert response.json()["results"] == []

    def test_team_member_sees_team_granted_devices(self, client):
        member = UserFactory()
        team = TeamFactory()
        TeamMembershipFactory(team=team, user=member)
        athlete_profile = AthleteProfileFactory()
        device = DeviceFactory(owner=athlete_profile.user)
        TeamAccessGrantFactory(athlete=athlete_profile, grantee_team=team, scopes=[SCOPE])
        response = client.get("/api/v1/devices/", **auth_headers(member))
        assert [d["id"] for d in response.json()["results"]] == [str(device.pk)]

    def test_superuser_sees_all(self, client):
        superuser = UserFactory(is_superuser=True)
        devices = [DeviceFactory() for _ in range(3)]
        response = client.get("/api/v1/devices/", **auth_headers(superuser))
        assert {d["id"] for d in response.json()["results"]} == {str(d.pk) for d in devices}

    def test_list_emits_audit_event_for_granted_reads(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        DeviceFactory(owner=athlete_profile.user)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE])
        client.get("/api/v1/devices/", **auth_headers(coach_user))
        event = AuditEvent.objects.get(action="device.listed")
        assert event.actor_id == coach_user.pk
        assert event.metadata == {"granted_devices": 1}

    def test_list_no_audit_event_for_own_devices_only(self, client):
        owner = UserFactory()
        DeviceFactory(owner=owner)
        client.get("/api/v1/devices/", **auth_headers(owner))
        assert not AuditEvent.objects.filter(action="device.listed").exists()

    def test_filter_by_status(self, client):
        owner = UserFactory()
        model = DeviceModelFactory()
        active = DeviceFactory(owner=owner, device_model=model)
        retired = DeviceFactory(owner=owner, device_model=model, status=Device.Status.RETIRED)
        response = client.get("/api/v1/devices/?status=retired", **auth_headers(owner))
        assert [d["id"] for d in response.json()["results"]] == [str(retired.pk)]
        assert str(active.pk) not in {d["id"] for d in response.json()["results"]}

    def test_filter_by_device_model(self, client):
        owner = UserFactory()
        model_a = DeviceModelFactory()
        model_b = DeviceModelFactory()
        device_a = DeviceFactory(owner=owner, device_model=model_a)
        DeviceFactory(owner=owner, device_model=model_b)
        response = client.get(f"/api/v1/devices/?device_model={model_a.pk}", **auth_headers(owner))
        assert [d["id"] for d in response.json()["results"]] == [str(device_a.pk)]


class TestDeviceCreate:
    def test_creates_device_for_connected_user(self, client):
        owner = UserFactory(email="sportif@example.com")
        model = _prototype_v1()
        payload = {
            "device_model": str(model.pk),
            "serial_number": "SN-0001",
            "name": "Capteur main droite",
            "firmware_version": "1.2.3",
        }
        response = post_json(client, "/api/v1/devices/", payload, **auth_headers(owner))
        assert response.status_code == 201, response.data
        body = response.json()
        assert body["owner_email"] == "sportif@example.com"
        assert body["serial_number"] == "SN-0001"
        assert body["status"] == "active"
        assert body["device_model"]["name"] == "prototype_v1"
        assert Device.objects.filter(owner=owner, serial_number="SN-0001").exists()

    def test_register_prototype_v1_and_find_it_back(self, client):
        """Critère d'acceptation : enregistrer un capteur ``prototype_v1`` et le retrouver."""
        owner = UserFactory()
        model = _prototype_v1()
        payload = {"device_model": str(model.pk), "serial_number": "SN-PROTO-1"}
        response = post_json(client, "/api/v1/devices/", payload, **auth_headers(owner))
        assert response.status_code == 201, response.data
        created_id = response.json()["id"]
        listing = client.get("/api/v1/devices/", **auth_headers(owner)).json()["results"]
        assert [d["id"] for d in listing] == [created_id]

    def test_duplicate_serial_same_model_conflict(self, client):
        owner = UserFactory()
        model = DeviceModelFactory()
        payload = {"device_model": str(model.pk), "serial_number": "SN-DUP"}
        assert (
            post_json(client, "/api/v1/devices/", payload, **auth_headers(owner)).status_code == 201
        )
        response = post_json(client, "/api/v1/devices/", payload, **auth_headers(owner))
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "conflict"
        assert "SN-DUP" in error["message"]

    def test_same_serial_different_model_allowed(self, client):
        """Le même serial peut exister sur deux modèles différents (identité du capteur)."""
        owner = UserFactory()
        model_a = DeviceModelFactory()
        model_b = DeviceModelFactory()
        payload_a = {"device_model": str(model_a.pk), "serial_number": "SN-SHARED"}
        payload_b = {"device_model": str(model_b.pk), "serial_number": "SN-SHARED"}
        assert (
            post_json(client, "/api/v1/devices/", payload_a, **auth_headers(owner)).status_code
            == 201
        )
        assert (
            post_json(client, "/api/v1/devices/", payload_b, **auth_headers(owner)).status_code
            == 201
        )

    def test_unknown_model_refused(self, client):
        owner = UserFactory()
        response = post_json(
            client,
            "/api/v1/devices/",
            {"device_model": "00000000-0000-4000-8000-000000000000", "serial_number": "SN-X"},
            **auth_headers(owner),
        )
        assert response.status_code == 400

    def test_missing_serial_refused(self, client):
        owner = UserFactory()
        model = DeviceModelFactory()
        response = post_json(
            client, "/api/v1/devices/", {"device_model": str(model.pk)}, **auth_headers(owner)
        )
        assert response.status_code == 400

    def test_anonymous_cannot_create(self, client):
        model = _prototype_v1()
        response = post_json(
            client,
            "/api/v1/devices/",
            {"device_model": str(model.pk), "serial_number": "SN-X"},
        )
        assert response.status_code == 401
