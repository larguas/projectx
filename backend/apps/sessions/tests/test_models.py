"""Tests du modèle ``Session`` : machine à états et contraintes multi-appareils.

La machine à états est la SEULE source de vérité des transitions (les services
l'appliquent sous verrouillage, cf. ``test_services.py``) ; les contraintes
d'unicité ``(session, device)`` et ``(session, device, channel_id)``
garantissent le support multi-appareils sans doublons.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.devices.tests.factories import DeviceFactory
from apps.exercises.tests.factories import MuscleFactory
from apps.sessions.models import Session, SessionChannel, SessionDevice
from apps.sessions.tests.factories import (
    SessionChannelFactory,
    SessionDeviceFactory,
    SessionFactory,
)


class TestStateMachine:
    """``can_transition_to`` / ``is_terminal`` : la machine à états du modèle."""

    def test_created_can_go_recording_or_cancelled(self):
        session = SessionFactory()
        assert session.status == Session.Status.CREATED
        assert session.can_transition_to(Session.Status.RECORDING)
        assert session.can_transition_to(Session.Status.CANCELLED)

    def test_recording_can_go_completed_cancelled_or_failed(self):
        session = SessionFactory(status=Session.Status.RECORDING)
        assert session.can_transition_to(Session.Status.COMPLETED)
        assert session.can_transition_to(Session.Status.CANCELLED)
        assert session.can_transition_to(Session.Status.FAILED)

    def test_created_cannot_skip_recording(self):
        """``created → completed`` n'existe pas : il faut enregistrer d'abord."""
        session = SessionFactory()
        assert not session.can_transition_to(Session.Status.COMPLETED)
        assert not session.can_transition_to(Session.Status.FAILED)

    def test_terminal_states_have_no_outgoing_transition(self):
        for terminal in (
            Session.Status.COMPLETED,
            Session.Status.CANCELLED,
            Session.Status.FAILED,
        ):
            session = SessionFactory(status=terminal)
            assert session.is_terminal
            for target in Session.Status.values:
                assert not session.can_transition_to(target), f"{terminal} → {target}"

    def test_non_terminal_states_are_not_terminal(self):
        assert not SessionFactory().is_terminal
        assert not SessionFactory(status=Session.Status.RECORDING).is_terminal

    def test_unknown_target_refused(self):
        session = SessionFactory()
        assert not session.can_transition_to("inexistant")


class TestMultiDeviceConstraints:
    """Unicité des appareils et des canaux par appareil (support multi-appareils)."""

    def test_same_device_twice_in_one_session_refused(self):
        session = SessionFactory()
        device = DeviceFactory()
        SessionDeviceFactory(session=session, device=device)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SessionDevice.objects.create(session=session, device=device)

    def test_same_device_allowed_in_two_sessions(self):
        """La contrainte est par SÉANCE — un capteur sert plusieurs séances."""
        device = DeviceFactory()
        SessionDeviceFactory(device=device)
        SessionDeviceFactory(device=device)  # autre séance : autorisé

    def test_duplicate_channel_per_session_device_refused(self):
        session = SessionFactory()
        device = DeviceFactory()
        muscle = MuscleFactory()
        SessionChannelFactory(session=session, device=device, channel_id=3, muscle=muscle)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SessionChannel.objects.create(
                    session=session, device=device, channel_id=3, muscle=muscle
                )

    def test_same_channel_id_allowed_on_two_devices(self):
        """Le canal 1 du capteur A et le canal 1 du capteur B coexistent."""
        session = SessionFactory()
        muscle = MuscleFactory()
        SessionChannelFactory(session=session, device=DeviceFactory(), channel_id=1, muscle=muscle)
        SessionChannelFactory(session=session, device=DeviceFactory(), channel_id=1, muscle=muscle)

    def test_device_role_default_is_primary(self):
        session = SessionFactory()
        link = SessionDevice.objects.create(session=session, device=DeviceFactory())
        assert link.role == SessionDevice.Role.PRIMARY
