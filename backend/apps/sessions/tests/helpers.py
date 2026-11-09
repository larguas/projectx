"""Aides partagées aux tests de services de la feature 06 (app ``sessions``)."""

from apps.exercises.tests.factories import MuscleFactory
from apps.sessions.models import Session, SessionChannel

SCOPE_READ = "sessions:read"
SCOPE_WRITE = "sessions:write"


def channel_entry(device, channel_id=1, data_type=SessionChannel.DataType.EMG_RAW, **overrides):
    """Entrée de canal au format ``SessionChannelInputSerializer.validated_data``."""
    entry = {
        "device": device,
        "channel_id": channel_id,
        "muscle": MuscleFactory(),
        "side": SessionChannel.Side.NA,
        "data_type": data_type,
        "units": "",
    }
    entry.update(overrides)
    return entry


def create_payload(athlete, channels=None, **overrides):
    """Payload au format ``SessionCreateSerializer.validated_data``."""
    payload = {
        "athlete": athlete,
        "session_type": Session.SessionType.TRAINING,
        "setup": None,
        "calibration_type": None,
        "exercise": None,
        "workout": None,
        "source": Session.Source.MOBILE,
        "protocol_version": 1,
        "notes": "",
        "acquisition_config": {},
        "channels": channels or [],
    }
    payload.update(overrides)
    return payload
