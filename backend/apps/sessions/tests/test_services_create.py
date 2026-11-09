"""Tests de ``services.create_session`` : règles de création d'une séance.

- sans setup : ``setup_declared = False`` + avertissement ``setup_not_declared`` ;
- avec setup : canaux copiés (muscle/côté figés), calibrations applicables gelées,
  marqueur ``used_at`` posé par mise à jour en base ciblée (point d'extension 05b)
  — à la PREMIÈRE utilisation seulement ; un canal de setup sans capteur est
  refusé (``setup_incomplete``, 409) ;
- droit d'écriture du créateur sur le sportif (``sessions:write``) ;
- accessibilité de chaque appareil au demandeur + compatibilité des canaux avec
  les capacités du modèle d'appareil (``DeviceModel.capabilities``).
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.coaches.tests.factories import CoachProfileFactory
from apps.devices.tests.factories import DeviceFactory, DeviceModelFactory
from apps.exercises.tests.factories import MuscleFactory
from apps.sessions import services
from apps.sessions.models import Session, SessionDevice
from apps.setups.models import SensorSetup
from apps.setups.tests.factories import (
    CalibrationFactory,
    SensorSetupFactory,
    SetupChannelFactory,
)
from apps.teams.tests.factories import AccessGrantFactory

from .helpers import SCOPE_READ, SCOPE_WRITE, channel_entry, create_payload


def _coach(user):
    return CoachProfileFactory(user=user)


class TestCreateWithoutSetup:
    def test_sets_setup_declared_false_and_warning(self):
        profile = AthleteProfileFactory()
        device = DeviceFactory(owner=profile.user)
        session, warnings = services.create_session(
            profile.user,
            create_payload(profile, channels=[channel_entry(device)]),
        )
        assert session.status == Session.Status.CREATED
        assert session.setup is None
        assert session.setup_declared is False
        assert warnings == ["setup_not_declared"]

    def test_channels_and_devices_created(self):
        profile = AthleteProfileFactory()
        device_a = DeviceFactory(owner=profile.user)
        device_b = DeviceFactory(owner=profile.user)
        session, _ = services.create_session(
            profile.user,
            create_payload(
                profile,
                channels=[channel_entry(device_a), channel_entry(device_b, channel_id=2)],
            ),
        )
        assert session.channels.count() == 2
        roles = {link.device_id: link.role for link in session.devices.all()}
        # Premier appareil distinct (ordre de déclaration) = primaire.
        assert roles[device_a.pk] == SessionDevice.Role.PRIMARY
        assert roles[device_b.pk] == SessionDevice.Role.SECONDARY

    def test_session_without_channels_has_no_devices(self):
        profile = AthleteProfileFactory()
        session, _ = services.create_session(profile.user, create_payload(profile))
        assert session.channels.count() == 0
        assert session.devices.count() == 0


class TestCreateWithSetup:
    def test_copies_channels_with_frozen_muscle_and_side(self):
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        device = DeviceFactory(owner=profile.user)
        muscle_a, muscle_b = MuscleFactory(), MuscleFactory()
        SetupChannelFactory(setup=setup, device=device, channel_id=1, muscle=muscle_a, side="left")
        SetupChannelFactory(setup=setup, device=device, channel_id=2, muscle=muscle_b, side="right")

        session, warnings = services.create_session(
            profile.user, create_payload(profile, setup=setup)
        )

        assert warnings == []
        assert session.setup_declared is True
        copied = {(c.device_id, c.channel_id): c for c in session.channels.all()}
        assert len(copied) == 2
        first = copied[(device.pk, 1)]
        assert first.muscle_id == muscle_a.pk
        assert first.side == "left"
        # La référence au canal d'origine est conservée (tracabilité du placement).
        assert first.setup_channel is not None
        assert session.devices.count() == 1
        assert session.devices.first().role == SessionDevice.Role.PRIMARY

    def test_freezes_applicable_calibrations_on_channels(self):
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        device = DeviceFactory(owner=profile.user)
        setup_channel = SetupChannelFactory(setup=setup, device=device, channel_id=1)
        CalibrationFactory(setup=setup, setup_channel=setup_channel)

        session, _ = services.create_session(profile.user, create_payload(profile, setup=setup))

        copied = session.channels.get(channel_id=1)
        # Copie GELÉE : type/valeurs/version d'algorithme — jamais l'identifiant.
        assert copied.calibration == [
            {"type": "mvc", "values": {"mvc_rms": 42.5}, "algorithm_version": "1.0"}
        ]

    def test_invalidated_calibration_not_frozen(self):
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        device = DeviceFactory(owner=profile.user)
        setup_channel = SetupChannelFactory(setup=setup, device=device, channel_id=1)
        CalibrationFactory(
            setup=setup,
            setup_channel=setup_channel,
            invalidated_at=timezone.now() - timedelta(days=1),
        )

        session, _ = services.create_session(profile.user, create_payload(profile, setup=setup))

        assert session.channels.get(channel_id=1).calibration is None

    def test_setup_channel_without_device_refused(self):
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        SetupChannelFactory(setup=setup, device=None)  # placement générique incomplet

        with pytest.raises(services.SessionsServiceError) as excinfo:
            services.create_session(profile.user, create_payload(profile, setup=setup))
        assert excinfo.value.code == "setup_incomplete"
        assert not Session.objects.filter(athlete=profile).exists()

    def test_used_at_set_on_first_use_via_db_update(self):
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        device = DeviceFactory(owner=profile.user)
        SetupChannelFactory(setup=setup, device=device)
        assert setup.used_at is None

        services.create_session(profile.user, create_payload(profile, setup=setup))

        setup.refresh_from_db()
        assert setup.used_at is not None

    def test_reusing_used_setup_keeps_original_used_at(self):
        """Le marqueur n'est posé qu'à la PREMIÈRE utilisation : une séance peut
        réutiliser un setup déjà utilisé (même placement, nouveau jour)."""
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        device = DeviceFactory(owner=profile.user)
        SetupChannelFactory(setup=setup, device=device)

        services.create_session(profile.user, create_payload(profile, setup=setup))
        first_used_at = SensorSetup.objects.get(pk=setup.pk).used_at
        assert first_used_at is not None

        services.create_session(profile.user, create_payload(profile, setup=setup))
        setup.refresh_from_db()
        assert setup.used_at == first_used_at


class TestCreateAccessControl:
    def test_coach_with_read_only_grant_refused(self):
        profile = AthleteProfileFactory()
        coach_user = UserFactory()
        AccessGrantFactory(athlete=profile, grantee_coach=_coach(coach_user), scopes=[SCOPE_READ])

        with pytest.raises(services.SessionsServiceError) as excinfo:
            services.create_session(coach_user, create_payload(profile))
        assert excinfo.value.code == "forbidden"

    def test_user_without_grant_refused(self):
        profile = AthleteProfileFactory()
        stranger = UserFactory()
        with pytest.raises(services.SessionsServiceError) as excinfo:
            services.create_session(stranger, create_payload(profile))
        assert excinfo.value.code == "forbidden"

    def test_coach_with_write_grant_can_create(self):
        profile = AthleteProfileFactory()
        coach_user = UserFactory()
        AccessGrantFactory(athlete=profile, grantee_coach=_coach(coach_user), scopes=[SCOPE_WRITE])

        session, _ = services.create_session(coach_user, create_payload(profile))
        assert session.created_by_id == coach_user.pk


class TestCreateDeviceChecks:
    def test_device_not_accessible_refused(self):
        """Un appareil non lisible par le demandeur (ni propriétaire, ni grant)
        ne peut pas être utilisé dans la séance."""
        profile = AthleteProfileFactory()
        foreign_device = DeviceFactory()  # propriétaire tiers sans lien
        with pytest.raises(services.SessionsServiceError) as excinfo:
            services.create_session(
                profile.user, create_payload(profile, channels=[channel_entry(foreign_device)])
            )
        assert excinfo.value.code == "forbidden"

    def test_coach_needs_devices_read_grant_for_athlete_device(self):
        """Le coach utilise le capteur DE SON SPORTIF : il en a besoin la lecture
        (grant ``devices:read``) en plus de ``sessions:write``."""
        profile = AthleteProfileFactory()
        device = DeviceFactory(owner=profile.user)
        coach_user = UserFactory()
        coach = _coach(coach_user)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_WRITE])

        with pytest.raises(services.SessionsServiceError) as excinfo:
            services.create_session(
                coach_user, create_payload(profile, channels=[channel_entry(device)])
            )
        assert excinfo.value.code == "forbidden"

        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=["devices:read"])
        session, _ = services.create_session(
            coach_user, create_payload(profile, channels=[channel_entry(device)])
        )
        assert session.channels.count() == 1

    def test_emg_channels_max_enforced(self):
        profile = AthleteProfileFactory()
        model = DeviceModelFactory(capabilities={"emg_channels_max": 2})
        device = DeviceFactory(owner=profile.user, device_model=model)
        with pytest.raises(services.SessionsServiceError) as excinfo:
            services.create_session(
                profile.user,
                create_payload(
                    profile,
                    channels=[channel_entry(device, channel_id=i) for i in (1, 2, 3)],
                ),
            )
        assert excinfo.value.code == "capability_exceeded"

    def test_imu_channel_refused_when_model_has_no_imu(self):
        profile = AthleteProfileFactory()
        model = DeviceModelFactory(capabilities={"emg_channels_max": 8, "imu": False})
        device = DeviceFactory(owner=profile.user, device_model=model)
        with pytest.raises(services.SessionsServiceError) as excinfo:
            services.create_session(
                profile.user,
                create_payload(profile, channels=[channel_entry(device, data_type="imu_accel")]),
            )
        assert excinfo.value.code == "capability_exceeded"

    def test_imu_channel_allowed_when_model_has_imu(self):
        profile = AthleteProfileFactory()
        model = DeviceModelFactory(capabilities={"emg_channels_max": 8, "imu": True})
        device = DeviceFactory(owner=profile.user, device_model=model)
        session, _ = services.create_session(
            profile.user,
            create_payload(profile, channels=[channel_entry(device, data_type="imu_accel")]),
        )
        assert session.channels.count() == 1

    def test_missing_capability_not_enforced(self):
        """Capacité absente du JSON : modèle non documenté — on ne bloque jamais."""
        profile = AthleteProfileFactory()
        model = DeviceModelFactory(capabilities={})
        device = DeviceFactory(owner=profile.user, device_model=model)
        session, _ = services.create_session(
            profile.user,
            create_payload(
                profile, channels=[channel_entry(device, channel_id=i) for i in (1, 2, 3)]
            ),
        )
        assert session.channels.count() == 3
