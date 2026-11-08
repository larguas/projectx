"""Factories de test de la feature 05b (app ``setups``).

Usage : ``from apps.setups.tests.factories import SensorSetupFactory, …``.

Note : un setup « utilisé » ne l'est que via le marqueur ``used_at``, posé par
une mise à jour en base ciblée (point d'extension unique de la feature 06) —
jamais par ``save()`` (un setup figé refuse d'être sauvegardé au niveau
modèle). Cf. ``mark_used`` ci-dessous.
"""

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.athletes.tests.factories import AthleteProfileFactory
from apps.exercises.tests.factories import MuscleFactory
from apps.setups.models import Calibration, SensorSetup, SetupChannel


class SensorSetupFactory(DjangoModelFactory):
    """Setup de placement, version 1, non utilisé (``used_at`` vide)."""

    class Meta:
        model = SensorSetup

    athlete = factory.SubFactory(AthleteProfileFactory)
    name = factory.Sequence(lambda n: f"Setup {n}")
    version = 1
    detail_level = SensorSetup.DetailLevel.SIMPLE
    is_current = True
    created_by = factory.LazyAttribute(lambda o: o.athlete.user)
    notes = ""


class SetupChannelFactory(DjangoModelFactory):
    """Canal de placement (sans capteur par défaut — placement générique)."""

    class Meta:
        model = SetupChannel

    setup = factory.SubFactory(SensorSetupFactory)
    channel_id = 1
    muscle = factory.SubFactory(MuscleFactory)
    side = SetupChannel.Side.LEFT


class CalibrationFactory(DjangoModelFactory):
    """Calibration valide (non invalidée, non expirée) d'une version de setup.

    ``athlete`` est dérivé du setup : une calibration appartient au sportif du
    setup qu'elle calibre.
    """

    class Meta:
        model = Calibration

    setup = factory.SubFactory(SensorSetupFactory)
    # ``LazyAttribute`` (et non ``RelatedFactory``, qui ne s'exécute qu'APRÈS
    # la sauvegarde du parent — trop tard pour une colonne NOT NULL) : le canal
    # est créé et lié au setup de la calibration AVANT l'INSERT.
    setup_channel = factory.LazyAttribute(lambda o: SetupChannelFactory(setup=o.setup))
    athlete = factory.LazyAttribute(lambda o: o.setup.athlete)
    type = Calibration.Type.MVC
    values = {"mvc_rms": 42.5}
    algorithm_version = "1.0"
    valid_from = factory.LazyFunction(timezone.now)


def mark_used(setup: SensorSetup) -> SensorSetup:
    """Marque un setup comme utilisé — point d'extension unique de la feature 06.

    Reproduit ce que fera la feature 06 à la première utilisation par une
    séance : mise à jour en base ciblée (``filter(...).update()``) qui ne
    passe PAS par ``save()`` (un setup figé refuse d'être sauvegardé au niveau
    modèle). Retourne l'instance rechargée.
    """
    SensorSetup.objects.filter(pk=setup.pk).update(used_at=timezone.now())
    return SensorSetup.objects.get(pk=setup.pk)
