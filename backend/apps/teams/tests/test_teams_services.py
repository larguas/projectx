"""Tests des services équipes/membres (``apps.teams.services``).

Couvre : création d'équipe (propriétaire + membership actif), invitations par
le propriétaire uniquement, acceptation, retrait (propriétaire ou le membre
lui-même), suppression en cascade.
"""

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.teams import services
from apps.teams.models import TeamMembership
from apps.teams.tests.factories import (
    TeamAccessGrantFactory,
    TeamFactory,
    TeamMembershipFactory,
)
from core import access

SCOPE = "sessions:read"


class TestCreateTeam:
    def test_creator_becomes_owner_with_active_membership(self):
        user = UserFactory()
        team = services.create_team(user, "Les Rapides")
        assert team.owner_id == user.pk
        membership = TeamMembership.objects.get(team=team, user=user)
        assert membership.role == TeamMembership.Role.OWNER
        assert membership.status == TeamMembership.Status.ACTIVE

    def test_creator_can_see_team(self):
        user = UserFactory()
        team = services.create_team(user, "Les Rapides")
        assert services.get_team_for_user(team.pk, user) is not None


class TestAddMember:
    def test_owner_invites_member_pending(self):
        team = TeamFactory()
        invited = UserFactory()
        membership = services.add_member(team, invited, actor=team.owner, role="athlete")
        assert membership.status == TeamMembership.Status.PENDING
        assert membership.role == TeamMembership.Role.ATHLETE

    def test_non_owner_cannot_invite(self):
        team = TeamFactory()
        stranger = UserFactory()
        invited = UserFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.add_member(team, invited, actor=stranger, role="athlete")
        assert exc.value.code == "forbidden"

    def test_owner_role_not_assignable(self):
        team = TeamFactory()
        invited = UserFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.add_member(team, invited, actor=team.owner, role="owner")
        assert exc.value.code == "invalid_role"

    def test_owner_cannot_be_reinvited(self):
        team = TeamFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.add_member(team, team.owner, actor=team.owner, role="coach")
        assert exc.value.code == "conflict"

    def test_existing_membership_conflict(self):
        team = TeamFactory()
        invited = UserFactory()
        TeamMembershipFactory(team=team, user=invited)
        with pytest.raises(services.TeamsServiceError) as exc:
            services.add_member(team, invited, actor=team.owner, role="coach")
        assert exc.value.code == "conflict"

    def test_removed_membership_can_be_reinvited(self):
        team = TeamFactory()
        invited = UserFactory()
        TeamMembershipFactory(team=team, user=invited, status=TeamMembership.Status.REMOVED)
        membership = services.add_member(team, invited, actor=team.owner, role="coach")
        assert membership.status == TeamMembership.Status.PENDING


class TestAcceptMember:
    def test_invited_member_accepts(self):
        team = TeamFactory()
        invited = UserFactory()
        services.add_member(team, invited, actor=team.owner, role="athlete")
        accepted = services.accept_member(team, invited)
        assert accepted.status == TeamMembership.Status.ACTIVE

    def test_double_accept_conflict(self):
        team = TeamFactory()
        invited = UserFactory()
        services.add_member(team, invited, actor=team.owner, role="athlete")
        services.accept_member(team, invited)
        with pytest.raises(services.TeamsServiceError) as exc:
            services.accept_member(team, invited)
        assert exc.value.code == "conflict"

    def test_no_invitation_not_found(self):
        team = TeamFactory()
        stranger = UserFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.accept_member(team, stranger)
        assert exc.value.code == "not_found"


class TestRemoveMember:
    def test_owner_removes_member(self):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        removed = services.remove_member(team, member, actor=team.owner)
        assert removed.status == TeamMembership.Status.REMOVED

    def test_member_removes_themselves(self):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        removed = services.remove_member(team, member, actor=member)
        assert removed.status == TeamMembership.Status.REMOVED

    def test_stranger_cannot_remove(self):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        stranger = UserFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.remove_member(team, member, actor=stranger)
        assert exc.value.code == "forbidden"

    def test_owner_cannot_be_removed(self):
        team = TeamFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.remove_member(team, team.owner, actor=team.owner)
        assert exc.value.code == "conflict"

    def test_removal_kills_team_grant_access_immediately(self):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        athlete = AthleteProfileFactory()
        TeamAccessGrantFactory(athlete=athlete, grantee_team=team, scopes=[SCOPE])
        assert access.can_access_athlete(member, athlete, SCOPE) is True
        services.remove_member(team, member, actor=member)
        assert access.can_access_athlete(member, athlete, SCOPE) is False


class TestDeleteTeam:
    def test_owner_deletes_team(self):
        team = TeamFactory()
        services.delete_team(team, team.owner)
        from apps.teams.models import Team

        assert not Team.objects.filter(pk=team.pk).exists()

    def test_non_owner_cannot_delete(self):
        team = TeamFactory()
        stranger = UserFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.delete_team(team, stranger)
        assert exc.value.code == "forbidden"

    def test_deleting_team_kills_grants_to_it(self):
        from apps.athletes.tests.factories import AthleteProfileFactory

        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        athlete = AthleteProfileFactory()
        TeamAccessGrantFactory(athlete=athlete, grantee_team=team, scopes=[SCOPE])
        assert access.can_access_athlete(member, athlete, SCOPE) is True
        services.delete_team(team, team.owner)
        assert access.can_access_athlete(member, athlete, SCOPE) is False
