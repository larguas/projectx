"""Tests des canaux et appareils d'une séance : ``GET/PUT .../channels|devices/``.

GET : liste (lecture non-propriétaire tracée — ``session.viewed``). PUT :
remplacement INTÉGRAL, uniquement pendant ``created`` (``locked``, 409 sinon) ;
les canaux re-dérivent les appareils (premier appareil distinct = primaire) ;
les rôles d'appareils exigent l'ensemble EXACT de ceux référencés par les
canaux (``channels_reference_device`` / ``device_not_in_session``, 409).
"""

import json

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.devices.tests.factories import DeviceFactory, DeviceModelFactory
from apps.exercises.tests.factories import MuscleFactory
from apps.sessions.tests.factories import make_session
from apps.teams.tests.factories import AccessGrantFactory


def _channels_url(session):
    return f"/api/v1/sessions/{session.pk}/channels/"


def _devices_url(session):
    return f"/api/v1/sessions/{session.pk}/devices/"


def _channel(device, channel_id=1, muscle=None):
    return {
        "device": str(device.pk),
        "channel_id": channel_id,
        "muscle": str((muscle or MuscleFactory()).pk),
    }


def _put(client, user, url, payload):
    return client.put(
        url, data=json.dumps(payload), content_type="application/json", **auth_headers(user)
    )


def _coach_with_grant(athlete, scopes):
    coach_user = UserFactory()
    coach = CoachProfileFactory(user=coach_user)
    AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=scopes)
    return coach_user


class TestChannelsList:
    def test_owner_lists_channels(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device = DeviceFactory(owner=owner)
        session = make_session(athlete=profile, channels=[(device, 1), (device, 2)])
        response = client.get(_channels_url(session), **auth_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert [c["channel_id"] for c in body] == [1, 2]
        assert all(c["device"]["id"] == str(device.pk) for c in body)

    def test_non_owner_read_audited(self, client):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        coach_user = _coach_with_grant(profile, ["sessions:read"])
        response = client.get(_channels_url(session), **auth_headers(coach_user))
        assert response.status_code == 200
        assert AuditEvent.objects.filter(action="session.viewed", actor_id=coach_user.pk).exists()

    def test_coach_without_grant_404(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        session = make_session()
        assert client.get(_channels_url(session), **auth_headers(coach_user)).status_code == 404


class TestChannelsReplace:
    def test_put_replaces_and_derives_devices(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device_a = DeviceFactory(owner=owner)
        device_b = DeviceFactory(owner=owner)
        session = make_session(athlete=profile, channels=[(device_a, 1)])

        payload = {"channels": [_channel(device_b, 3), _channel(device_b, 4)]}
        response = _put(client, owner, _channels_url(session), payload)
        assert response.status_code == 200
        assert [c["channel_id"] for c in response.json()] == [3, 4]

        session.refresh_from_db()
        assert not session.channels.filter(device=device_a).exists()
        # Le premier appareil distinct de la déclaration devient primaire.
        roles = {d.device_id: d.role for d in session.devices.all()}
        assert roles == {device_b.pk: "primary"}

    def test_put_empty_list_clears(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device = DeviceFactory(owner=owner)
        session = make_session(athlete=profile, channels=[(device, 1)])
        response = _put(client, owner, _channels_url(session), {"channels": []})
        assert response.status_code == 200
        assert response.json() == []
        session.refresh_from_db()
        assert not session.channels.exists()
        assert not session.devices.exists()

    def test_put_locked_outside_created(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device = DeviceFactory(owner=owner)
        session = make_session(athlete=profile, status="recording", channels=[(device, 1)])
        response = _put(client, owner, _channels_url(session), {"channels": [_channel(device, 9)]})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "locked"

    def test_put_capability_exceeded(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        limited = DeviceModelFactory(capabilities={"emg_channels_max": 1})
        device = DeviceFactory(owner=owner, device_model=limited)
        session = make_session(athlete=profile, channels=[(device, 1)])
        payload = {"channels": [_channel(device, 1), _channel(device, 2)]}
        response = _put(client, owner, _channels_url(session), payload)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "capability_exceeded"

    def test_put_read_only_grant_refused(self, client):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        coach_user = _coach_with_grant(profile, ["sessions:read"])
        response = _put(client, coach_user, _channels_url(session), {"channels": []})
        assert response.status_code == 403


class TestDevicesList:
    def test_owner_lists_devices_with_roles(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device_a = DeviceFactory(owner=owner)
        device_b = DeviceFactory(owner=owner)
        session = make_session(athlete=profile, channels=[(device_a, 1), (device_b, 1)])
        response = client.get(_devices_url(session), **auth_headers(owner))
        assert response.status_code == 200
        roles = {d["device"]["id"]: d["role"] for d in response.json()}
        assert roles == {str(device_a.pk): "primary", str(device_b.pk): "secondary"}


class TestDevicesReplace:
    def _session_with_two_devices(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device_a = DeviceFactory(owner=owner)
        device_b = DeviceFactory(owner=owner)
        session = make_session(athlete=profile, channels=[(device_a, 1), (device_b, 1)])
        return owner, session, device_a, device_b

    def test_swap_roles(self, client):
        owner, session, device_a, device_b = self._session_with_two_devices(client)
        payload = {
            "devices": [
                {"device": str(device_a.pk), "role": "secondary"},
                {"device": str(device_b.pk), "role": "primary"},
            ]
        }
        response = _put(client, owner, _devices_url(session), payload)
        assert response.status_code == 200
        roles = {d.device_id: d.role for d in session.devices.all()}
        assert roles == {device_a.pk: "secondary", device_b.pk: "primary"}

    def test_missing_device_refused(self, client):
        owner, session, _a, device_b = self._session_with_two_devices(client)
        payload = {"devices": [{"device": str(device_b.pk), "role": "primary"}]}
        response = _put(client, owner, _devices_url(session), payload)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "channels_reference_device"

    def test_extra_device_refused(self, client):
        owner, session, device_a, device_b = self._session_with_two_devices(client)
        stranger = DeviceFactory(owner=owner)
        # Tous les appareils référencés + un intrus : l'excédent est refusé.
        payload = {
            "devices": [
                {"device": str(device_a.pk), "role": "primary"},
                {"device": str(device_b.pk), "role": "secondary"},
                {"device": str(stranger.pk), "role": "secondary"},
            ]
        }
        response = _put(client, owner, _devices_url(session), payload)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "device_not_in_session"

    def test_two_primaries_refused(self, client):
        owner, session, device_a, device_b = self._session_with_two_devices(client)
        payload = {
            "devices": [
                {"device": str(device_a.pk), "role": "primary"},
                {"device": str(device_b.pk), "role": "primary"},
            ]
        }
        response = _put(client, owner, _devices_url(session), payload)
        assert response.status_code == 409

    def test_locked_outside_created(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device = DeviceFactory(owner=owner)
        session = make_session(athlete=profile, status="recording", channels=[(device, 1)])
        payload = {"devices": [{"device": str(device.pk), "role": "primary"}]}
        response = _put(client, owner, _devices_url(session), payload)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "locked"
