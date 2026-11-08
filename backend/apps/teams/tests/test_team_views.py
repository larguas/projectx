"""Tests de l'API équipes : ``/api/v1/teams/`` et ``/api/v1/teams/{id}/members/``.

La liste ne contient que les équipes où l'utilisateur est membre actif ou en
attente ; le détail/membres exigent une membership non retirée (404 sinon).
"""

import json

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.audit.models import AuditEvent
from apps.teams.models import TeamMembership
from apps.teams.tests.factories import (
    TeamFactory,
    TeamMembershipFactory,
)


def patch_json(client, url: str, payload: dict, **extra):
    return client.patch(url, data=json.dumps(payload), content_type="application/json", **extra)


class TestTeamListCreate:
    def test_anonymous_refused(self, client):
        assert client.get("/api/v1/teams/").status_code == 401
        assert post_json(client, "/api/v1/teams/", {"name": "X Y"}).status_code == 401

    def test_list_shows_active_and_pending_memberships_only(self, client):
        user = UserFactory()
        active_team = TeamFactory()
        pending_team = TeamFactory()
        removed_team = TeamFactory()
        TeamMembershipFactory(team=active_team, user=user, status=TeamMembership.Status.ACTIVE)
        TeamMembershipFactory(team=pending_team, user=user, status=TeamMembership.Status.PENDING)
        TeamMembershipFactory(team=removed_team, user=user, status=TeamMembership.Status.REMOVED)
        response = client.get("/api/v1/teams/", **auth_headers(user))
        assert response.status_code == 200
        ids = {t["id"] for t in response.json()["results"]}
        assert ids == {str(active_team.pk), str(pending_team.pk)}

    def test_create_team_makes_user_owner(self, client):
        user = UserFactory(email="owner@example.com")
        response = post_json(
            client, "/api/v1/teams/", {"name": "Les Rapides"}, **auth_headers(user)
        )
        assert response.status_code == 201, response.data
        body = response.json()
        assert body["name"] == "Les Rapides"
        assert body["owner_id"] == str(user.pk)
        assert body["owner_email"] == "owner@example.com"
        membership = TeamMembership.objects.get(team_id=body["id"], user=user)
        assert membership.role == TeamMembership.Role.OWNER
        assert AuditEvent.objects.filter(action="team.created").exists()

    def test_create_team_name_too_short_refused(self, client):
        user = UserFactory()
        response = post_json(client, "/api/v1/teams/", {"name": "X"}, **auth_headers(user))
        assert response.status_code == 400


class TestTeamDetail:
    def test_member_reads_team(self, client):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        response = client.get(f"/api/v1/teams/{team.pk}/", **auth_headers(member))
        assert response.status_code == 200
        assert response.json()["name"] == team.name

    def test_non_member_gets_404(self, client):
        team = TeamFactory()
        stranger = UserFactory()
        response = client.get(f"/api/v1/teams/{team.pk}/", **auth_headers(stranger))
        assert response.status_code == 404

    def test_owner_renames_team(self, client):
        team = TeamFactory()
        response = patch_json(
            client, f"/api/v1/teams/{team.pk}/", {"name": "Nouveau nom"}, **auth_headers(team.owner)
        )
        assert response.status_code == 200, response.data
        team.refresh_from_db()
        assert team.name == "Nouveau nom"
        assert AuditEvent.objects.filter(action="team.updated").exists()

    def test_non_owner_cannot_rename(self, client):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        response = patch_json(
            client, f"/api/v1/teams/{team.pk}/", {"name": "Piratage"}, **auth_headers(member)
        )
        assert response.status_code == 403

    def test_owner_deletes_team(self, client):
        team = TeamFactory()
        response = client.delete(f"/api/v1/teams/{team.pk}/", **auth_headers(team.owner))
        assert response.status_code == 204
        from apps.teams.models import Team

        assert not Team.objects.filter(pk=team.pk).exists()
        assert AuditEvent.objects.filter(action="team.deleted").exists()

    def test_non_owner_cannot_delete(self, client):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        response = client.delete(f"/api/v1/teams/{team.pk}/", **auth_headers(member))
        assert response.status_code == 403


class TestMemberEndpoints:
    def test_anonymous_refused(self, client):
        team = TeamFactory()
        assert client.get(f"/api/v1/teams/{team.pk}/members/").status_code == 401

    def test_member_lists_members_without_removed(self, client):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        kept = TeamMembershipFactory(team=team, user=UserFactory())
        removed = TeamMembershipFactory(
            team=team, user=UserFactory(), status=TeamMembership.Status.REMOVED
        )
        response = client.get(f"/api/v1/teams/{team.pk}/members/", **auth_headers(member))
        assert response.status_code == 200
        ids = {m["id"] for m in response.json()["results"]}
        assert str(kept.pk) in ids
        assert str(removed.pk) not in ids

    def test_non_member_gets_404_on_members(self, client):
        team = TeamFactory()
        stranger = UserFactory()
        response = client.get(f"/api/v1/teams/{team.pk}/members/", **auth_headers(stranger))
        assert response.status_code == 404

    def test_owner_invites_member(self, client):
        team = TeamFactory()
        invited = UserFactory(email="invited@example.com")
        response = post_json(
            client,
            f"/api/v1/teams/{team.pk}/members/",
            {"user_id": str(invited.pk), "role": "athlete"},
            **auth_headers(team.owner),
        )
        assert response.status_code == 201, response.data
        body = response.json()
        assert body["status"] == TeamMembership.Status.PENDING
        assert body["email"] == "invited@example.com"
        assert AuditEvent.objects.filter(action="team_member.invited").exists()

    def test_non_owner_cannot_invite(self, client):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        response = post_json(
            client,
            f"/api/v1/teams/{team.pk}/members/",
            {"user_id": str(UserFactory().pk), "role": "coach"},
            **auth_headers(member),
        )
        assert response.status_code == 403

    def test_invite_owner_role_refused(self, client):
        team = TeamFactory()
        response = post_json(
            client,
            f"/api/v1/teams/{team.pk}/members/",
            {"user_id": str(UserFactory().pk), "role": "owner"},
            **auth_headers(team.owner),
        )
        assert response.status_code == 400

    def test_member_removes_themselves(self, client):
        team = TeamFactory()
        member = UserFactory()
        membership = TeamMembershipFactory(team=team, user=member)
        response = client.delete(
            f"/api/v1/teams/{team.pk}/members/{member.pk}/", **auth_headers(member)
        )
        assert response.status_code == 204
        membership.refresh_from_db()
        assert membership.status == TeamMembership.Status.REMOVED
        assert AuditEvent.objects.filter(action="team_member.removed").exists()

    def test_owner_removes_member(self, client):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        response = client.delete(
            f"/api/v1/teams/{team.pk}/members/{member.pk}/", **auth_headers(team.owner)
        )
        assert response.status_code == 204

    def test_stranger_cannot_remove_member(self, client):
        team = TeamFactory()
        member = UserFactory()
        TeamMembershipFactory(team=team, user=member)
        stranger = UserFactory()
        response = client.delete(
            f"/api/v1/teams/{team.pk}/members/{member.pk}/", **auth_headers(stranger)
        )
        assert response.status_code == 404
