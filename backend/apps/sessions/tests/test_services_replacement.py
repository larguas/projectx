"""Tests de ``replace_channels`` / ``replace_devices`` (remplacement intégral).

- canaux : uniquement pendant ``created`` (``locked``, 409) ; les lignes
  ``SessionDevice`` sont RE-DÉRIVÉES des nouveaux canaux (premier appareil
  distinct en ordre de déclaration = primaire) — l'invariant « appareils ==
  canaux » est conservé par construction ; mêmes contrôles d'accessibilité et
  de capacités que la création ;
- appareils : uniquement pendant ``created`` ; l'ensemble fourni doit être
  EXACTEMENT celui référencé par les canaux (``channels_reference_device`` /
  ``device_not_in_session``, 409) ; au plus un primaire.
"""

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.devices.tests.factories import DeviceFactory, DeviceModelFactory
from apps.sessions import services
from apps.sessions.models import SessionChannel, SessionDevice
from apps.sessions.tests.factories import make_session

from .helpers import channel_entry


def _error_code(fn, *args):
    with pytest.raises(services.SessionsServiceError) as excinfo:
        fn(*args)
    return excinfo.value.code


class TestReplaceChannels:
    def test_replaces_channels_and_derives_devices(self):
        profile = AthleteProfileFactory()
        old_device = DeviceFactory(owner=profile.user)
        session = make_session(athlete=profile, channels=[(old_device, 1)])

        new_device_a = DeviceFactory(owner=profile.user)
        new_device_b = DeviceFactory(owner=profile.user)
        result = services.replace_channels(
            profile.user,
            str(session.pk),
            [channel_entry(new_device_a), channel_entry(new_device_b, channel_id=2)],
        )

        assert result.channels.count() == 2
        assert not SessionChannel.objects.filter(session=result, device=old_device).exists()
        roles = {link.device_id: link.role for link in result.devices.all()}
        # Les anciens appareils sont remplacés ; nouveau premier = primaire.
        assert set(roles) == {new_device_a.pk, new_device_b.pk}
        assert roles[new_device_a.pk] == SessionDevice.Role.PRIMARY
        assert roles[new_device_b.pk] == SessionDevice.Role.SECONDARY

    def test_empty_list_removes_all_channels_and_devices(self):
        profile = AthleteProfileFactory()
        device = DeviceFactory(owner=profile.user)
        session = make_session(athlete=profile, channels=[(device, 1)])

        result = services.replace_channels(profile.user, str(session.pk), [])

        assert result.channels.count() == 0
        assert result.devices.count() == 0

    @pytest.mark.parametrize("status", ["recording", "completed", "cancelled", "failed"])
    def test_locked_outside_created(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)
        device = DeviceFactory(owner=profile.user)

        assert _error_code(
            services.replace_channels, profile.user, str(session.pk), [channel_entry(device)]
        ) == ("locked")

    def test_user_without_write_grant_refused(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        device = DeviceFactory(owner=profile.user)
        stranger = UserFactory()

        assert _error_code(
            services.replace_channels, stranger, str(session.pk), [channel_entry(device)]
        ) == ("forbidden")

    def test_capability_exceeded(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        model = DeviceModelFactory(capabilities={"emg_channels_max": 1})
        device = DeviceFactory(owner=profile.user, device_model=model)

        assert (
            _error_code(
                services.replace_channels,
                profile.user,
                str(session.pk),
                [channel_entry(device, channel_id=i) for i in (1, 2)],
            )
            == "capability_exceeded"
        )


class TestReplaceDevices:
    def test_swaps_roles(self):
        profile = AthleteProfileFactory()
        device_a = DeviceFactory(owner=profile.user)
        device_b = DeviceFactory(owner=profile.user)
        session = make_session(athlete=profile, channels=[(device_a, 1), (device_b, 1)])
        assert session.devices.get(device_id=device_a.pk).role == SessionDevice.Role.PRIMARY

        result = services.replace_devices(
            profile.user,
            str(session.pk),
            [
                {"device": device_a, "role": "secondary"},
                {"device": device_b, "role": "primary"},
            ],
        )

        roles = {link.device_id: link.role for link in result.devices.all()}
        assert roles[device_a.pk] == SessionDevice.Role.SECONDARY
        assert roles[device_b.pk] == SessionDevice.Role.PRIMARY

    def test_missing_referenced_device_refused(self):
        profile = AthleteProfileFactory()
        device_a = DeviceFactory(owner=profile.user)
        device_b = DeviceFactory(owner=profile.user)
        session = make_session(athlete=profile, channels=[(device_a, 1), (device_b, 2)])

        assert (
            _error_code(
                services.replace_devices,
                profile.user,
                str(session.pk),
                [{"device": device_a, "role": "primary"}],
            )
            == "channels_reference_device"
        )

    def test_extra_device_refused(self):
        profile = AthleteProfileFactory()
        device_a = DeviceFactory(owner=profile.user)
        outsider = DeviceFactory(owner=profile.user)
        session = make_session(athlete=profile, channels=[(device_a, 1)])

        assert (
            _error_code(
                services.replace_devices,
                profile.user,
                str(session.pk),
                [
                    {"device": device_a, "role": "primary"},
                    {"device": outsider, "role": "secondary"},
                ],
            )
            == "device_not_in_session"
        )

    def test_two_primaries_refused(self):
        profile = AthleteProfileFactory()
        device_a = DeviceFactory(owner=profile.user)
        device_b = DeviceFactory(owner=profile.user)
        session = make_session(athlete=profile, channels=[(device_a, 1), (device_b, 2)])

        assert (
            _error_code(
                services.replace_devices,
                profile.user,
                str(session.pk),
                [
                    {"device": device_a, "role": "primary"},
                    {"device": device_b, "role": "primary"},
                ],
            )
            == "device_not_in_session"
        )

    @pytest.mark.parametrize("status", ["recording", "completed", "cancelled", "failed"])
    def test_locked_outside_created(self, status):
        profile = AthleteProfileFactory()
        device = DeviceFactory(owner=profile.user)
        session = make_session(athlete=profile, status=status, channels=[(device, 1)])

        assert (
            _error_code(
                services.replace_devices,
                profile.user,
                str(session.pk),
                [{"device": device, "role": "primary"}],
            )
            == "locked"
        )

    def test_user_without_write_grant_refused(self):
        profile = AthleteProfileFactory()
        device = DeviceFactory(owner=profile.user)
        session = make_session(athlete=profile, channels=[(device, 1)])
        stranger = UserFactory()

        assert (
            _error_code(
                services.replace_devices,
                stranger,
                str(session.pk),
                [{"device": device, "role": "primary"}],
            )
            == "forbidden"
        )
