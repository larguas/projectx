"""Tests de ``POST /api/v1/sessions/`` : création d'une séance.

Droits du créateur sur le sportif (scope ``sessions:write`` — 403 sinon) ;
avertissement ``setup_not_declared`` dans la RÉPONSE (et le détail) quand la
séance est créée sans setup ; canaux copiés depuis le setup fourni (la
déclaration manuelle est alors refusée, 400) ; séance ``calibration`` exige
setup ET type (400) ; doublons ``(device, channel_id)`` refusés (400) ;
appareils inaccessibles ou capacités dépassées (403 / 409).
"""

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.coaches.tests.factories import CoachProfileFactory
from apps.devices.tests.factories import DeviceFactory, DeviceModelFactory
from apps.exercises.tests.factories import MuscleFactory
from apps.setups.tests.factories import SensorSetupFactory, SetupChannelFactory
from apps.teams.tests.factories import AccessGrantFactory

CREATE_URL = "/api/v1/sessions/"


def _payload(athlete, **overrides):
    payload = {
        "athlete": str(athlete.pk),
        "session_type": "training",
    }
    payload.update(overrides)
    return payload


def _channel(device, channel_id=1, muscle=None, data_type="emg_raw"):
    return {
        "device": str(device.pk),
        "channel_id": channel_id,
        "muscle": str((muscle or MuscleFactory()).pk),
        "data_type": data_type,
    }


def _coach_with_grant(athlete, scopes):
    coach_user = UserFactory()
    coach = CoachProfileFactory(user=coach_user)
    AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=scopes)
    return coach_user


class TestCreatePermissions:
    def test_anonymous_refused(self, client):
        profile = AthleteProfileFactory()
        assert post_json(client, CREATE_URL, _payload(profile)).status_code == 401

    def test_owner_creates_for_own_athlete(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        response = post_json(client, CREATE_URL, _payload(profile), **auth_headers(owner))
        assert response.status_code == 201
        assert response.json()["status"] == "created"

    def test_coach_with_write_grant_creates(self, client):
        profile = AthleteProfileFactory()
        coach_user = _coach_with_grant(profile, ["sessions:write"])
        response = post_json(client, CREATE_URL, _payload(profile), **auth_headers(coach_user))
        assert response.status_code == 201

    def test_coach_with_read_only_grant_refused(self, client):
        profile = AthleteProfileFactory()
        coach_user = _coach_with_grant(profile, ["sessions:read"])
        response = post_json(client, CREATE_URL, _payload(profile), **auth_headers(coach_user))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_coach_without_grant_refused(self, client):
        profile = AthleteProfileFactory()
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        response = post_json(client, CREATE_URL, _payload(profile), **auth_headers(coach_user))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_superuser_creates(self, client):
        superuser = UserFactory(is_superuser=True)
        profile = AthleteProfileFactory()
        response = post_json(client, CREATE_URL, _payload(profile), **auth_headers(superuser))
        assert response.status_code == 201


class TestCreateContract:
    def test_without_setup_warns_in_response_and_detail(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        response = post_json(client, CREATE_URL, _payload(profile), **auth_headers(owner))
        assert response.status_code == 201
        body = response.json()
        assert body["warnings"] == ["setup_not_declared"]
        assert body["setup_declared"] is False

    def test_with_setup_copies_channels_and_marks_used(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device = DeviceFactory(owner=owner)
        setup = SensorSetupFactory(athlete=profile)
        SetupChannelFactory(setup=setup, device=device, channel_id=1)

        response = post_json(
            client, CREATE_URL, _payload(profile, setup=str(setup.pk)), **auth_headers(owner)
        )
        assert response.status_code == 201
        body = response.json()
        assert body["warnings"] == []
        assert body["setup_declared"] is True
        assert [c["channel_id"] for c in body["channels"]] == [1]

        setup.refresh_from_db()
        assert setup.used_at is not None  # premier usage : le setup est figé

    def test_setup_with_manual_channels_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device = DeviceFactory(owner=owner)
        setup = SensorSetupFactory(athlete=profile)
        payload = _payload(profile, setup=str(setup.pk), channels=[_channel(device)])
        response = post_json(client, CREATE_URL, payload, **auth_headers(owner))
        assert response.status_code == 400
        assert "channels" in response.json()["error"]["details"]

    def test_calibration_requires_setup_and_type(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        payload = _payload(profile, session_type="calibration")
        response = post_json(client, CREATE_URL, payload, **auth_headers(owner))
        assert response.status_code == 400
        details = response.json()["error"]["details"]
        assert "setup" in details and "calibration_type" in details

    def test_calibration_with_setup_but_no_type_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup = SensorSetupFactory(athlete=profile)
        response = post_json(
            client,
            CREATE_URL,
            _payload(profile, session_type="calibration", setup=str(setup.pk)),
            **auth_headers(owner),
        )
        assert response.status_code == 400
        assert "calibration_type" in response.json()["error"]["details"]

    def test_calibration_with_setup_and_type_ok(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device = DeviceFactory(owner=owner)
        setup = SensorSetupFactory(athlete=profile)
        SetupChannelFactory(setup=setup, device=device, channel_id=1)
        response = post_json(
            client,
            CREATE_URL,
            _payload(
                profile, session_type="calibration", setup=str(setup.pk), calibration_type="mvc"
            ),
            **auth_headers(owner),
        )
        assert response.status_code == 201
        assert response.json()["session_type"] == "calibration"

    def test_duplicate_device_channel_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device = DeviceFactory(owner=owner)
        payload = _payload(profile, channels=[_channel(device, 1), _channel(device, 1)])
        response = post_json(client, CREATE_URL, payload, **auth_headers(owner))
        assert response.status_code == 400

    def test_missing_athlete_refused(self, client):
        owner = UserFactory()
        response = post_json(
            client, CREATE_URL, {"session_type": "training"}, **auth_headers(owner)
        )
        assert response.status_code == 400


class TestCreateDeviceChecks:
    def test_foreign_device_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        foreign_device = DeviceFactory()  # d'un autre utilisateur, sans grant
        payload = _payload(profile, channels=[_channel(foreign_device)])
        response = post_json(client, CREATE_URL, payload, **auth_headers(owner))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_emg_channels_max_exceeded(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        limited_model = DeviceModelFactory(capabilities={"emg_channels_max": 1})
        device = DeviceFactory(owner=owner, device_model=limited_model)
        payload = _payload(profile, channels=[_channel(device, 1), _channel(device, 2)])
        response = post_json(client, CREATE_URL, payload, **auth_headers(owner))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "capability_exceeded"

    def test_imu_channel_refused_without_imu_capability(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        no_imu_model = DeviceModelFactory(capabilities={"imu": False})
        device = DeviceFactory(owner=owner, device_model=no_imu_model)
        payload = _payload(profile, channels=[_channel(device, data_type="imu_accel")])
        response = post_json(client, CREATE_URL, payload, **auth_headers(owner))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "capability_exceeded"
