"""Factories de test de la feature 02, réutilisables par les autres apps.

Usage : ``from apps.accounts.tests.factories import UserFactory``.
"""

import secrets
from datetime import timedelta

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.models import DeviceAuthorization, User, generate_user_code, hash_code

DEFAULT_TEST_PASSWORD = "S3cure-Passw0rd!-EMG"


class UserFactory(DjangoModelFactory):
    """Utilisateur de test ; l'email est unique et normalisé en minuscules."""

    class Meta:
        model = User
        django_get_or_create = ("email",)
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"
    is_active = True

    @factory.post_generation
    def password(self, create, extracted):
        """Fixe le mot de passe (persisté explicitement, sans save implicite)."""
        if not create:
            return
        self.set_password(extracted or DEFAULT_TEST_PASSWORD)
        self.save(update_fields=["password"])


class DeviceAuthorizationFactory(DjangoModelFactory):
    """Autorisation de client de test (codes hachés, TTL 5 minutes)."""

    class Meta:
        model = DeviceAuthorization

    user = factory.SubFactory(UserFactory)
    client_type = DeviceAuthorization.ClientType.PC_AGENT
    client_name = "EMG PC Agent"
    client_version = "1.0.0"
    status = DeviceAuthorization.Status.PENDING
    device_code_hash = factory.LazyFunction(lambda: hash_code(secrets.token_urlsafe(32)))
    user_code_hash = factory.LazyFunction(lambda: hash_code(generate_user_code()))
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(minutes=5))
