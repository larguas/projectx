"""Factories de test de la feature 03 (app ``athletes``).

Usage : ``from apps.athletes.tests.factories import AthleteProfileFactory``.
"""

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.athletes.models import AthleteProfile


class AthleteProfileFactory(DjangoModelFactory):
    """Profil sportif rattaché à un utilisateur de test."""

    class Meta:
        model = AthleteProfile

    user = factory.SubFactory(UserFactory)
    date_of_birth = "1990-05-15"
    sport = "Tennis"
    notes = ""
