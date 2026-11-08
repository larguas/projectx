"""Tests des modèles de la feature 03 (app ``coaches``)."""

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.tests.factories import UserFactory
from apps.athletes.models import AthleteProfile
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.coaches.models import CoachProfile
from apps.coaches.tests.factories import CoachProfileFactory


class TestCoachProfile:
    def test_one_profile_per_user(self):
        user = UserFactory()
        CoachProfileFactory(user=user)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CoachProfile.objects.create(user=user)

    def test_deleting_user_cascades_profile(self):
        profile = CoachProfileFactory()
        user = profile.user
        user.delete()
        assert not CoachProfile.objects.filter(pk=profile.pk).exists()

    def test_str_uses_owner_email(self):
        profile = CoachProfileFactory(user=UserFactory(email="coach@example.com"))
        assert "coach@example.com" in str(profile)

    def test_user_can_hold_both_profiles(self):
        # Un utilisateur cumule les rôles sportif et coach (un profil par rôle).
        user = UserFactory()
        athlete = AthleteProfileFactory(user=user)
        coach = CoachProfileFactory(user=user)
        assert AthleteProfile.objects.get(user=user).pk == athlete.pk
        assert CoachProfile.objects.get(user=user).pk == coach.pk
