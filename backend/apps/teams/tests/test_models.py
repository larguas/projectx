"""Tests des modèles de la feature 03 (app ``teams``).

Contraintes en base : XOR bénéficiaire/type du grant, membership unique non
retiré par ``(team, user)`` ; comportement ``is_active`` et cascades.
"""

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.coaches.tests.factories import CoachProfileFactory
from apps.teams.models import AccessGrant, TeamMembership
from apps.teams.tests.factories import (
    AccessGrantFactory,
    TeamAccessGrantFactory,
    TeamFactory,
    TeamMembershipFactory,
)


class TestTeamMembershipConstraints:
    def test_duplicate_non_removed_membership_refused(self):
        team = TeamFactory()
        user = UserFactory()
        TeamMembershipFactory(team=team, user=user)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                TeamMembership.objects.create(team=team, user=user, role="coach")

    def test_removed_membership_allows_reinvite(self):
        team = TeamFactory()
        user = UserFactory()
        first = TeamMembershipFactory(team=team, user=user)
        first.status = TeamMembership.Status.REMOVED
        first.save(update_fields=["status"])
        second = TeamMembership.objects.create(team=team, user=user, role="coach")
        assert second.pk != first.pk


class TestAccessGrantConstraints:
    def test_coach_type_without_coach_refused(self):
        athlete = AthleteProfileFactory()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                AccessGrant.objects.create(
                    athlete=athlete,
                    granted_by=athlete.user,
                    grantee_type="coach",
                    grantee_team=TeamFactory(),
                )

    def test_team_type_without_team_refused(self):
        athlete = AthleteProfileFactory()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                AccessGrant.objects.create(
                    athlete=athlete,
                    granted_by=athlete.user,
                    grantee_type="team",
                    grantee_coach=CoachProfileFactory(),
                )

    def test_both_grantees_refused(self):
        athlete = AthleteProfileFactory()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                AccessGrant.objects.create(
                    athlete=athlete,
                    granted_by=athlete.user,
                    grantee_type="coach",
                    grantee_coach=CoachProfileFactory(),
                    grantee_team=TeamFactory(),
                )

    def test_valid_coach_grant_ok(self):
        grant = AccessGrantFactory()
        assert grant.grantee_coach is not None
        assert grant.grantee_team is None

    def test_valid_team_grant_ok(self):
        grant = TeamAccessGrantFactory()
        assert grant.grantee_team is not None
        assert grant.grantee_coach is None


class TestGrantIsActive:
    def test_active_without_expiry(self):
        assert AccessGrantFactory(expires_at=None).is_active() is True

    def test_active_with_future_expiry(self):
        grant = AccessGrantFactory(expires_at=timezone.now() + timezone.timedelta(days=1))
        assert grant.is_active() is True

    def test_active_with_past_expiry(self):
        grant = AccessGrantFactory(expires_at=timezone.now() - timezone.timedelta(days=1))
        assert grant.is_active() is False

    @pytest.mark.parametrize(
        "status",
        [AccessGrant.Status.PENDING, AccessGrant.Status.REVOKED, AccessGrant.Status.EXPIRED],
    )
    def test_non_active_status(self, status):
        assert AccessGrantFactory(status=status).is_active() is False


class TestCascades:
    def test_deleting_coach_deletes_its_grants(self):
        grant = AccessGrantFactory()
        coach = grant.grantee_coach
        coach.delete()
        assert not AccessGrant.objects.filter(pk=grant.pk).exists()

    def test_deleting_athlete_deletes_its_grants(self):
        grant = AccessGrantFactory()
        athlete = grant.athlete
        athlete.delete()
        assert not AccessGrant.objects.filter(pk=grant.pk).exists()

    def test_deleting_team_cascades_memberships_and_grants(self):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        grant = TeamAccessGrantFactory(grantee_team=team)
        team.delete()
        assert not TeamMembership.objects.filter(team_id=team.pk).exists()
        assert not AccessGrant.objects.filter(pk=grant.pk).exists()

    def test_deleting_granted_by_protected(self):
        from django.db.models.deletion import ProtectedError

        grant = AccessGrantFactory()
        with pytest.raises(ProtectedError):
            grant.granted_by.delete()
