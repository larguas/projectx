"""Factories de test de la feature 03 (app ``coaches``).

Usage : ``from apps.coaches.tests.factories import CoachProfileFactory``.
"""

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.coaches.models import CoachProfile


class CoachProfileFactory(DjangoModelFactory):
    """Profil coach rattaché à un utilisateur de test."""

    class Meta:
        model = CoachProfile

    user = factory.SubFactory(UserFactory)
    organization_name = "EMG Coaching"
    bio = ""
