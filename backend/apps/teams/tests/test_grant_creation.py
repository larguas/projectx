"""Tests des services de partage (``apps.teams.services.grant_access``).

Règles critiques : création par le propriétaire uniquement, validation des
scopes centralisés, statuts pending (coach) / active (équipe), un seul grant
non révoqué par bénéficiaire.
"""

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.coaches.tests.factories import CoachProfileFactory
from apps.teams import services
from apps.teams.models import AccessGrant, TeamMembership
from apps.teams.tests.factories import TeamFactory, TeamMembershipFactory
from core import access

SCOPE = "sessions:read"


class TestGrantAccess:
    def test_coach_grant_created_pending(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        assert grant.status == AccessGrant.Status.PENDING
        assert grant.grantee_coach_id == coach.pk
        assert grant.granted_at is not None
        # Pending n'ouvre rien.
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is False

    def test_team_grant_created_active(self):
        athlete = AthleteProfileFactory()
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member, status=TeamMembership.Status.ACTIVE)
        grant = services.grant_access(athlete.user, athlete, "team", team.pk, [SCOPE])
        assert grant.status == AccessGrant.Status.ACTIVE
        assert grant.grantee_team_id == team.pk

    def test_only_profile_owner_can_grant(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        stranger = UserFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.grant_access(stranger, athlete, "coach", coach.pk, [SCOPE])
        assert exc.value.code == "forbidden"

    def test_unknown_scope_refused(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.grant_access(athlete.user, athlete, "coach", coach.pk, ["banane:read"])
        assert exc.value.code == "invalid_scope"

    def test_empty_scopes_refused(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.grant_access(athlete.user, athlete, "coach", coach.pk, [])
        assert exc.value.code == "invalid_scope"

    def test_scopes_deduplicated_in_grant(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(
            athlete.user, athlete, "coach", coach.pk, [SCOPE, "reports:read", SCOPE]
        )
        assert grant.scopes == [SCOPE, "reports:read"]

    def test_past_expiry_refused(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.grant_access(
                athlete.user,
                athlete,
                "coach",
                coach.pk,
                [SCOPE],
                expires_at=timezone.now() - timezone.timedelta(days=1),
            )
        assert exc.value.code == "invalid_expiry"

    def test_future_expiry_stored(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        expiry = timezone.now() + timezone.timedelta(days=30)
        grant = services.grant_access(
            athlete.user, athlete, "coach", coach.pk, [SCOPE], expires_at=expiry
        )
        assert grant.expires_at == expiry

    def test_unknown_coach_refused(self):
        athlete = AthleteProfileFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.grant_access(athlete.user, athlete, "coach", UserFactory().pk, [SCOPE])
        assert exc.value.code == "not_found"

    def test_unknown_team_refused(self):
        athlete = AthleteProfileFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.grant_access(athlete.user, athlete, "team", UserFactory().pk, [SCOPE])
        assert exc.value.code == "not_found"

    def test_invalid_grantee_type_refused(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.grant_access(athlete.user, athlete, "friend", coach.pk, [SCOPE])
        assert exc.value.code == "invalid_grantee"

    def test_second_non_revoked_grant_conflict(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        with pytest.raises(services.TeamsServiceError) as exc:
            services.grant_access(athlete.user, athlete, "coach", coach.pk, ["reports:read"])
        assert exc.value.code == "conflict"

    def test_recreate_after_revocation_allowed(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        first = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        services.revoke_grant(athlete.user, first.pk)
        second = services.grant_access(athlete.user, athlete, "coach", coach.pk, ["reports:read"])
        assert second.status == AccessGrant.Status.PENDING
        assert second.scopes == ["reports:read"]
