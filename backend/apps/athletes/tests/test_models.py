"""Tests des modèles de la feature 03 (app ``athletes``)."""

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.tests.factories import UserFactory
from apps.athletes.models import AthleteProfile
from apps.athletes.tests.factories import AthleteProfileFactory


class TestAthleteProfile:
    def test_one_profile_per_user(self):
        user = UserFactory()
        AthleteProfileFactory(user=user)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                AthleteProfile.objects.create(user=user, date_of_birth="1990-01-01")

    def test_deleting_user_cascades_profile(self):
        profile = AthleteProfileFactory()
        user = profile.user
        user.delete()
        assert not AthleteProfile.objects.filter(pk=profile.pk).exists()

    def test_str_uses_owner_email(self):
        profile = AthleteProfileFactory(user=UserFactory(email="jane@example.com"))
        assert "jane@example.com" in str(profile)

    def test_optional_fields_default_empty(self):
        profile = AthleteProfileFactory(
            sex="", height_cm=None, weight_kg=None, dominant_side="", sport="", notes=""
        )
        assert profile.sex == ""
        assert profile.height_cm is None
