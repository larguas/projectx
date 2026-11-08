"""Tests de l'API sportifs : ``GET/POST /api/v1/athletes/``.

La liste est filtrée par le sélecteur central (``core.access.granted_athletes``) :
un coach n'y voit QUE les sportifs qui lui ont accordé un grant actif.
"""

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.athletes.models import AthleteProfile
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.teams.models import AccessGrant
from apps.teams.tests.factories import (
    AccessGrantFactory,
    TeamAccessGrantFactory,
    TeamFactory,
    TeamMembershipFactory,
)

SCOPE = "sessions:read"


class TestAthleteList:
    def test_anonymous_refused(self, client):
        response = client.get("/api/v1/athletes/")
        assert response.status_code == 401

    def test_owner_sees_own_profile_only(self, client):
        owner = UserFactory()
        own = AthleteProfileFactory(user=owner)
        AthleteProfileFactory()  # profil tiers : invisible dans la liste de l'owner
        response = client.get("/api/v1/athletes/", **auth_headers(owner))
        assert response.status_code == 200
        results = response.json()["results"]
        assert [p["id"] for p in results] == [str(own.pk)]

    def test_coach_sees_only_granted_athletes(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        granted = AthleteProfileFactory()
        AthleteProfileFactory()  # sans grant : invisible pour le coach
        AccessGrantFactory(athlete=granted, grantee_coach=coach, scopes=[SCOPE])
        response = client.get("/api/v1/athletes/", **auth_headers(coach_user))
        assert response.status_code == 200
        results = response.json()["results"]
        assert [p["id"] for p in results] == [str(granted.pk)]

    def test_revoked_grant_excluded_from_list(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete = AthleteProfileFactory()
        AccessGrantFactory(athlete=athlete, grantee_coach=coach, status=AccessGrant.Status.REVOKED)
        response = client.get("/api/v1/athletes/", **auth_headers(coach_user))
        assert response.json()["results"] == []

    def test_team_member_sees_team_granted_athletes(self, client):
        member = UserFactory()
        team = TeamFactory()
        TeamMembershipFactory(team=team, user=member)
        athlete = AthleteProfileFactory()
        TeamAccessGrantFactory(athlete=athlete, grantee_team=team, scopes=[SCOPE])
        response = client.get("/api/v1/athletes/", **auth_headers(member))
        assert [p["id"] for p in response.json()["results"]] == [str(athlete.pk)]

    def test_superuser_sees_all(self, client):
        superuser = UserFactory(is_superuser=True)
        profiles = [AthleteProfileFactory() for _ in range(3)]
        response = client.get("/api/v1/athletes/", **auth_headers(superuser))
        results = response.json()["results"]
        assert {p["id"] for p in results} == {str(p.pk) for p in profiles}

    def test_list_emits_audit_event_for_granted_reads(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        granted = AthleteProfileFactory()
        AccessGrantFactory(athlete=granted, grantee_coach=coach, scopes=[SCOPE])
        assert not AuditEvent.objects.filter(action="athlete.listed").exists()
        client.get("/api/v1/athletes/", **auth_headers(coach_user))
        event = AuditEvent.objects.get(action="athlete.listed")
        assert event.actor_id == coach_user.pk
        assert event.metadata == {"granted_athletes": 1}

    def test_list_no_audit_event_for_own_profile_only(self, client):
        owner = UserFactory()
        AthleteProfileFactory(user=owner)
        client.get("/api/v1/athletes/", **auth_headers(owner))
        assert not AuditEvent.objects.filter(action="athlete.listed").exists()

    def test_filter_by_sport(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        tennis = AthleteProfileFactory(sport="Tennis")
        swimming = AthleteProfileFactory(sport="Natation")
        AccessGrantFactory(athlete=tennis, grantee_coach=coach, scopes=[SCOPE])
        AccessGrantFactory(athlete=swimming, grantee_coach=coach, scopes=[SCOPE])
        response = client.get("/api/v1/athletes/?sport=Natation", **auth_headers(coach_user))
        assert [p["id"] for p in response.json()["results"]] == [str(swimming.pk)]


class TestCreateAthleteProfile:
    def test_creates_own_profile(self, client):
        owner = UserFactory(email="sportif@example.com")
        payload = {"date_of_birth": "1992-03-10", "sex": "female", "sport": "Tennis"}
        response = post_json(client, "/api/v1/athletes/", payload, **auth_headers(owner))
        assert response.status_code == 201, response.data
        body = response.json()
        assert body["email"] == "sportif@example.com"
        assert body["sport"] == "Tennis"
        assert AthleteProfile.objects.filter(user=owner).exists()

    def test_second_creation_conflict(self, client):
        owner = UserFactory()
        payload = {"date_of_birth": "1992-03-10"}
        response = post_json(client, "/api/v1/athletes/", payload, **auth_headers(owner))
        assert response.status_code == 201
        response = post_json(client, "/api/v1/athletes/", payload, **auth_headers(owner))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_future_birth_date_refused(self, client):
        owner = UserFactory()
        response = post_json(
            client, "/api/v1/athletes/", {"date_of_birth": "2999-01-01"}, **auth_headers(owner)
        )
        assert response.status_code == 400

    def test_missing_birth_date_refused(self, client):
        owner = UserFactory()
        response = post_json(client, "/api/v1/athletes/", {}, **auth_headers(owner))
        assert response.status_code == 400

    def test_anonymous_cannot_create(self, client):
        response = post_json(client, "/api/v1/athletes/", {"date_of_birth": "1992-03-10"})
        assert response.status_code == 401
