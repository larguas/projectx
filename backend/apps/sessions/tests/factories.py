"""Factories de test de la feature 06 (app ``sessions``).

Usage : ``from apps.sessions.tests.factories import SessionFactory, …``.

Les factories créent des données HORS seed ; pour une séance COHÉRENTE
(canaux + appareils dérivés, premier appareil distinct = primaire), préférer
l'aide ``make_session`` ci-dessous plutôt que d'empiler les factories.
"""

import factory
from factory.django import DjangoModelFactory

from apps.athletes.tests.factories import AthleteProfileFactory
from apps.devices.tests.factories import DeviceFactory
from apps.exercises.tests.factories import MuscleFactory
from apps.sessions.models import Session, SessionAnnotation, SessionChannel, SessionDevice


class SessionFactory(DjangoModelFactory):
    """Séance ``created`` d'un sportif fictif (créateur = utilisateur du profil).

    Passer ``setup=…`` pose aussi ``setup_declared=True`` (cohérence métier :
    une séance créée depuis un setup a un placement déclaré).
    """

    class Meta:
        model = Session
        skip_postgeneration_save = True  # le hook ``setup`` sauvegarde explicitement

    athlete = factory.SubFactory(AthleteProfileFactory)
    created_by = factory.LazyAttribute(lambda o: o.athlete.user)
    session_type = Session.SessionType.TRAINING
    status = Session.Status.CREATED
    source = Session.Source.MOBILE
    protocol_version = 1
    notes = ""
    acquisition_config = {}

    @factory.post_generation
    def setup(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted is None:
            return
        self.setup = extracted
        self.setup_declared = True
        self.save()


class SessionDeviceFactory(DjangoModelFactory):
    """Appareil de séance (rôle ``primary`` par défaut)."""

    class Meta:
        model = SessionDevice

    session = factory.SubFactory(SessionFactory)
    device = factory.SubFactory(DeviceFactory)
    role = SessionDevice.Role.PRIMARY


class SessionChannelFactory(DjangoModelFactory):
    """Canal de séance rattaché à un appareil (muscle fictif)."""

    class Meta:
        model = SessionChannel

    session = factory.SubFactory(SessionFactory)
    device = factory.SubFactory(DeviceFactory)
    channel_id = 1
    muscle = factory.SubFactory(MuscleFactory)
    side = SessionChannel.Side.LEFT
    data_type = SessionChannel.DataType.EMG_RAW


class SessionAnnotationFactory(DjangoModelFactory):
    """Annotation de séance (auteur = créateur de la séance par défaut)."""

    class Meta:
        model = SessionAnnotation

    session = factory.SubFactory(SessionFactory)
    author = factory.LazyAttribute(lambda o: o.session.created_by)
    kind = SessionAnnotation.Kind.NOTE
    offset_ms = 0
    text = ""
    metadata = {}


def make_session(
    *,
    channels: list[tuple] | None = None,
    **session_kwargs,
) -> Session:
    """Séance + canaux + appareils COHÉRENTS (invariant « appareils == canaux »).

    ``channels`` : liste de ``(device, channel_id)`` — chaque appareil distinct
    devient une ligne ``SessionDevice``, le premier en ordre de déclaration
    prenant le rôle ``primary`` (même règle que la création d'une séance).
    ``None`` (défaut) : séance sans canal. Les autres arguments sont transmis
    à ``SessionFactory`` (``status=…``, ``athlete=…``, ``setup=…``, …).
    """
    session = SessionFactory(**session_kwargs)
    if not channels:
        return session
    muscle = MuscleFactory()
    SessionChannel.objects.bulk_create(
        SessionChannel(session=session, device=device, channel_id=channel_id, muscle=muscle)
        for device, channel_id in channels
    )
    distinct_devices = list(dict.fromkeys(device for device, _ in channels))
    roles = iter(
        [SessionDevice.Role.PRIMARY] + [SessionDevice.Role.SECONDARY] * (len(distinct_devices) - 1)
    )
    SessionDevice.objects.bulk_create(
        SessionDevice(session=session, device=device, role=next(roles))
        for device in distinct_devices
    )
    return session
