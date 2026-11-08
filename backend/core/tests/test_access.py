"""Tests exhaustifs du module d'accès central (``core.access``).

Cette API sera utilisée par toutes les features suivantes : la matrice
complète doit être couverte ici. Scénarios de référence :

- ``athlete`` : profil sportif (propriétaire ``athlete.user``) ;
- ``coach`` : profil coach (utilisateur ``coach.user``) ;
- grants fabriqués via ``AccessGrantFactory`` / ``TeamAccessGrantFactory``.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
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
from core import access

SCOPE = "sessions:read"
OTHER_SCOPE = "reports:read"


@pytest.fixture
def athlete():
    return AthleteProfileFactory()


@pytest.fixture
def coach():
    return CoachProfileFactory()


# --- can_access_athlete : matrice complète ------------------------------------


class TestCanAccessAthlete:
    def test_anonymous_refused(self, athlete):
        assert access.can_access_athlete(AnonymousUser(), athlete, SCOPE) is False

    def test_none_user_refused(self, athlete):
        assert access.can_access_athlete(None, athlete, SCOPE) is False

    def test_unknown_scope_refused_even_for_owner(self, athlete):
        # Deny by default : un scope inconnu n'ouvre rien, même au propriétaire.
        assert access.can_access_athlete(athlete.user, athlete, "bogus:scope") is False

    def test_unknown_scope_refused_even_for_superuser(self, athlete):
        superuser = UserFactory(is_superuser=True)
        assert access.can_access_athlete(superuser, athlete, "bogus:scope") is False

    def test_owner_allowed_any_known_scope(self, athlete):
        for scope in ("sessions:read", "analytics:read", "setups:write"):
            assert access.can_access_athlete(athlete.user, athlete, scope) is True

    def test_unrelated_user_refused(self, athlete):
        stranger = UserFactory()
        assert access.can_access_athlete(stranger, athlete, SCOPE) is False

    def test_coach_without_grant_refused(self, athlete, coach):
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is False

    def test_coach_with_active_grant_allowed(self, athlete, coach):
        AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=[SCOPE])
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is True

    def test_scope_isolation_sessions_read_does_not_open_reports(self, athlete, coach):
        # Un grant ``sessions:read`` n'ouvre pas ``reports:read``.
        AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=[SCOPE])
        assert access.can_access_athlete(coach.user, athlete, OTHER_SCOPE) is False

    def test_pending_grant_opens_nothing(self, athlete, coach):
        AccessGrantFactory(athlete=athlete, grantee_coach=coach, status=AccessGrant.Status.PENDING)
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is False

    def test_revoked_grant_opens_nothing(self, athlete, coach):
        AccessGrantFactory(
            athlete=athlete,
            grantee_coach=coach,
            status=AccessGrant.Status.REVOKED,
            revoked_at=timezone.now(),
        )
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is False

    def test_expired_grant_opens_nothing(self, athlete, coach):
        AccessGrantFactory(
            athlete=athlete,
            grantee_coach=coach,
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is False

    def test_future_expiry_grant_still_opens(self, athlete, coach):
        AccessGrantFactory(
            athlete=athlete,
            grantee_coach=coach,
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is True

    def test_team_member_with_active_membership_allowed(self, athlete):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member, status=TeamMembership.Status.ACTIVE)
        TeamAccessGrantFactory(athlete=athlete, grantee_team=team, scopes=[SCOPE])
        assert access.can_access_athlete(member, athlete, SCOPE) is True

    def test_pending_membership_opens_nothing(self, athlete):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member, status=TeamMembership.Status.PENDING)
        TeamAccessGrantFactory(athlete=athlete, grantee_team=team, scopes=[SCOPE])
        assert access.can_access_athlete(member, athlete, SCOPE) is False

    def test_removed_membership_opens_nothing(self, athlete):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member, status=TeamMembership.Status.REMOVED)
        TeamAccessGrantFactory(athlete=athlete, grantee_team=team, scopes=[SCOPE])
        assert access.can_access_athlete(member, athlete, SCOPE) is False

    def test_non_member_of_granted_team_refused(self, athlete):
        team = TeamFactory()
        stranger = UserFactory()
        TeamAccessGrantFactory(athlete=athlete, grantee_team=team, scopes=[SCOPE])
        assert access.can_access_athlete(stranger, athlete, SCOPE) is False

    def test_team_grant_scope_isolation(self, athlete):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member, status=TeamMembership.Status.ACTIVE)
        TeamAccessGrantFactory(athlete=athlete, grantee_team=team, scopes=[SCOPE])
        assert access.can_access_athlete(member, athlete, OTHER_SCOPE) is False

    def test_superuser_allowed(self, athlete):
        superuser = UserFactory(is_superuser=True)
        assert access.can_access_athlete(superuser, athlete, SCOPE) is True

    def test_dual_role_user_owner_side(self, athlete, coach):
        # Un utilisateur cumulant sportif + coach : côté propriétaire, accès direct.
        shared = UserFactory()
        athlete.user = shared
        athlete.save()
        coach.user = shared
        coach.save()
        assert access.can_access_athlete(shared, athlete, SCOPE) is True

    def test_dual_role_user_coach_side_needs_grant(self):
        # Côté coach, le même utilisateur a besoin d'un grant comme les autres.
        shared = UserFactory()
        profile = AthleteProfileFactory(user=shared)
        other_athlete = AthleteProfileFactory()
        AccessGrantFactory(
            athlete=other_athlete, grantee_coach=CoachProfileFactory(user=shared), scopes=[SCOPE]
        )
        assert access.can_access_athlete(shared, other_athlete, SCOPE) is True
        # Mais pas sur son propre profil vu « coach » sans grant (ici il est
        # propriétaire : l'accès passe par la propriété, pas par un grant).
        assert access.can_access_athlete(shared, profile, OTHER_SCOPE) is True

    def test_grant_for_other_coach_does_not_leak(self, athlete, coach):
        AccessGrantFactory(athlete=athlete, scopes=[SCOPE])  # à un autre coach
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is False


# --- visible_athletes : sélecteur de liste -------------------------------------


class TestVisibleAthletes:
    def test_anonymous_gets_empty(self):
        AthleteProfileFactory()
        assert list(access.visible_athletes(AnonymousUser(), SCOPE)) == []

    def test_unknown_scope_gets_empty(self, athlete):
        assert list(access.visible_athletes(athlete.user, "bogus:scope")) == []

    def test_owner_sees_only_own_profile(self, athlete):
        AthleteProfileFactory()  # un autre sportif, sans grant
        visible = access.visible_athletes(athlete.user, SCOPE)
        assert list(visible) == [athlete]

    def test_coach_sees_only_granted_athletes(self, coach):
        granted = AthleteProfileFactory()
        hidden = AthleteProfileFactory()
        AccessGrantFactory(athlete=granted, grantee_coach=coach, scopes=[SCOPE])
        visible = access.visible_athletes(coach.user, SCOPE)
        assert list(visible) == [granted]
        assert not visible.filter(pk=hidden.pk).exists()

    def test_revoked_grant_excluded_from_list(self, coach):
        revoked = AthleteProfileFactory()
        AccessGrantFactory(athlete=revoked, grantee_coach=coach, status=AccessGrant.Status.REVOKED)
        assert not access.visible_athletes(coach.user, SCOPE).filter(pk=revoked.pk).exists()

    def test_expired_grant_excluded_from_list(self, coach):
        expired = AthleteProfileFactory()
        AccessGrantFactory(
            athlete=expired,
            grantee_coach=coach,
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        assert not access.visible_athletes(coach.user, SCOPE).filter(pk=expired.pk).exists()

    def test_scope_isolation_in_list(self, coach):
        granted = AthleteProfileFactory()
        AccessGrantFactory(athlete=granted, grantee_coach=coach, scopes=[SCOPE])
        assert not access.visible_athletes(coach.user, OTHER_SCOPE).filter(pk=granted.pk).exists()

    def test_team_member_sees_team_granted_athletes(self):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member, status=TeamMembership.Status.ACTIVE)
        granted = AthleteProfileFactory()
        TeamAccessGrantFactory(athlete=granted, grantee_team=team, scopes=[SCOPE])
        visible = access.visible_athletes(member, SCOPE)
        assert list(visible) == [granted]

    def test_pending_membership_sees_nothing(self):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member, status=TeamMembership.Status.PENDING)
        granted = AthleteProfileFactory()
        TeamAccessGrantFactory(athlete=granted, grantee_team=team, scopes=[SCOPE])
        assert list(access.visible_athletes(member, SCOPE)) == []

    def test_superuser_sees_all(self):
        profiles = [AthleteProfileFactory() for _ in range(3)]
        superuser = UserFactory(is_superuser=True)
        visible = access.visible_athletes(superuser, SCOPE)
        assert set(visible) == set(profiles)

    def test_owner_plus_granted_combined(self, coach):
        own = AthleteProfileFactory(user=coach.user)
        granted = AthleteProfileFactory()
        AccessGrantFactory(athlete=granted, grantee_coach=coach, scopes=[SCOPE])
        visible = access.visible_athletes(coach.user, SCOPE)
        assert set(visible) == {own, granted}


# --- can_see_athlete / granted_athletes (niveau profil) ------------------------


class TestProfileLevelAccess:
    def test_can_see_athlete_owner(self, athlete):
        assert access.can_see_athlete(athlete.user, athlete) is True

    def test_can_see_athlete_coach_with_any_active_grant(self, athlete, coach):
        # Même si le scope du grant diffère : au niveau profil, un grant actif suffit.
        AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=[OTHER_SCOPE])
        assert access.can_see_athlete(coach.user, athlete) is True

    def test_can_see_athlete_revoked_grant_refused(self, athlete, coach):
        AccessGrantFactory(athlete=athlete, grantee_coach=coach, status=AccessGrant.Status.REVOKED)
        assert access.can_see_athlete(coach.user, athlete) is False

    def test_can_see_athlete_anonymous_refused(self, athlete):
        assert access.can_see_athlete(AnonymousUser(), athlete) is False

    def test_granted_athletes_includes_all_scopes(self, coach):
        a1 = AthleteProfileFactory()
        a2 = AthleteProfileFactory()
        AccessGrantFactory(athlete=a1, grantee_coach=coach, scopes=[SCOPE])
        AccessGrantFactory(athlete=a2, grantee_coach=coach, scopes=[OTHER_SCOPE])
        visible = access.granted_athletes(coach.user)
        assert set(visible) == {a1, a2}

    def test_granted_athletes_anonymous_empty(self):
        AthleteProfileFactory()
        assert list(access.granted_athletes(AnonymousUser())) == []

    def test_granted_athletes_superuser_all(self):
        profiles = [AthleteProfileFactory() for _ in range(2)]
        superuser = UserFactory(is_superuser=True)
        assert set(access.granted_athletes(superuser)) == set(profiles)
