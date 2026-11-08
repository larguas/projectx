"""Tests de l'API grants : ``/api/v1/access-grants/`` (+ accept/revoke).

Règles d'entrée : authentification (401) et email vérifié (403) pour créer ou
accepter un grant ; la révocation n'exige pas l'email vérifié. Chaque mutation
émet son événement d'audit.
"""

from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.teams.models import AccessGrant
from apps.teams.tests.factories import (
    AccessGrantFactory,
    TeamAccessGrantFactory,
    TeamFactory,
)

SCOPE = "sessions:read"


def verified_user():
    """Utilisateur dont l'email est vérifié (requis pour créer/accepter)."""
    user = UserFactory()
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at"])
    return user


class TestGrantList:
    def test_anonymous_refused(self, client):
        assert client.get("/api/v1/access-grants/").status_code == 401

    def test_owner_sees_grants_given(self, client):
        owner = verified_user()
        athlete = AthleteProfileFactory(user=owner)
        coach = CoachProfileFactory()
        AccessGrantFactory(athlete=athlete, granted_by=owner, grantee_coach=coach)
        response = client.get("/api/v1/access-grants/", **auth_headers(owner))
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["granted_by_id"] == str(owner.pk)

    def test_coach_sees_grants_addressed_to_him(self, client):
        coach_user = verified_user()
        coach = CoachProfileFactory(user=coach_user)
        athlete = AthleteProfileFactory()
        AccessGrantFactory(athlete=athlete, grantee_coach=coach)
        response = client.get("/api/v1/access-grants/", **auth_headers(coach_user))
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["grantee_coach_id"] == str(coach.pk)

    def test_unrelated_user_sees_nothing(self, client):
        stranger = verified_user()
        AccessGrantFactory()
        response = client.get("/api/v1/access-grants/", **auth_headers(stranger))
        assert response.json()["results"] == []


class TestGrantCreate:
    URL = "/api/v1/access-grants/"

    def test_anonymous_refused(self, client):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        payload = {
            "athlete": str(athlete.pk),
            "grantee_type": "coach",
            "grantee_id": str(coach.pk),
            "scopes": [SCOPE],
        }
        assert post_json(client, self.URL, payload).status_code == 401

    def test_unverified_email_refused(self, client):
        owner = UserFactory()  # email non vérifié
        athlete = AthleteProfileFactory(user=owner)
        coach = CoachProfileFactory()
        payload = {
            "athlete": str(athlete.pk),
            "grantee_type": "coach",
            "grantee_id": str(coach.pk),
            "scopes": [SCOPE],
        }
        response = post_json(client, self.URL, payload, **auth_headers(owner))
        assert response.status_code == 403

    def test_owner_creates_pending_coach_grant(self, client):
        owner = verified_user()
        athlete = AthleteProfileFactory(user=owner)
        coach = CoachProfileFactory()
        payload = {
            "athlete": str(athlete.pk),
            "grantee_type": "coach",
            "grantee_id": str(coach.pk),
            "scopes": [SCOPE, "reports:read"],
        }
        response = post_json(client, self.URL, payload, **auth_headers(owner))
        assert response.status_code == 201, response.data
        body = response.json()
        assert body["status"] == AccessGrant.Status.PENDING
        assert body["scopes"] == [SCOPE, "reports:read"]
        event = AuditEvent.objects.get(action="access_grant.created")
        assert event.actor_id == owner.pk

    def test_non_owner_cannot_grant(self, client):
        athlete = AthleteProfileFactory()
        stranger = verified_user()
        coach = CoachProfileFactory()
        payload = {
            "athlete": str(athlete.pk),
            "grantee_type": "coach",
            "grantee_id": str(coach.pk),
            "scopes": [SCOPE],
        }
        response = post_json(client, self.URL, payload, **auth_headers(stranger))
        assert response.status_code == 403

    def test_unknown_scope_refused(self, client):
        owner = verified_user()
        athlete = AthleteProfileFactory(user=owner)
        coach = CoachProfileFactory()
        payload = {
            "athlete": str(athlete.pk),
            "grantee_type": "coach",
            "grantee_id": str(coach.pk),
            "scopes": ["banane:read"],
        }
        response = post_json(client, self.URL, payload, **auth_headers(owner))
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_scope"

    def test_empty_scopes_refused(self, client):
        owner = verified_user()
        athlete = AthleteProfileFactory(user=owner)
        coach = CoachProfileFactory()
        payload = {
            "athlete": str(athlete.pk),
            "grantee_type": "coach",
            "grantee_id": str(coach.pk),
            "scopes": [],
        }
        response = post_json(client, self.URL, payload, **auth_headers(owner))
        assert response.status_code == 400

    def test_unknown_athlete_404(self, client):
        owner = verified_user()
        coach = CoachProfileFactory()
        payload = {
            "athlete": str(UserFactory().pk),
            "grantee_type": "coach",
            "grantee_id": str(coach.pk),
            "scopes": [SCOPE],
        }
        response = post_json(client, self.URL, payload, **auth_headers(owner))
        assert response.status_code == 404

    def test_team_grant_created_active(self, client):
        owner = verified_user()
        athlete = AthleteProfileFactory(user=owner)
        team = TeamFactory()
        payload = {
            "athlete": str(athlete.pk),
            "grantee_type": "team",
            "grantee_id": str(team.pk),
            "scopes": [SCOPE],
        }
        response = post_json(client, self.URL, payload, **auth_headers(owner))
        assert response.status_code == 201, response.data
        assert response.json()["status"] == AccessGrant.Status.ACTIVE

    def test_duplicate_grant_conflict(self, client):
        owner = verified_user()
        athlete = AthleteProfileFactory(user=owner)
        coach = CoachProfileFactory()
        payload = {
            "athlete": str(athlete.pk),
            "grantee_type": "coach",
            "grantee_id": str(coach.pk),
            "scopes": [SCOPE],
        }
        assert post_json(client, self.URL, payload, **auth_headers(owner)).status_code == 201
        response = post_json(client, self.URL, payload, **auth_headers(owner))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"


class TestGrantAccept:
    def test_anonymous_refused(self, client):
        grant = AccessGrantFactory()
        assert post_json(client, f"/api/v1/access-grants/{grant.pk}/accept/", {}).status_code == 401

    def test_unverified_email_refused(self, client):
        coach_user = UserFactory()  # non vérifié
        coach = CoachProfileFactory(user=coach_user)
        grant = AccessGrantFactory(grantee_coach=coach)
        response = post_json(
            client, f"/api/v1/access-grants/{grant.pk}/accept/", {}, **auth_headers(coach_user)
        )
        assert response.status_code == 403

    def test_beneficiary_accepts(self, client):
        coach_user = verified_user()
        coach = CoachProfileFactory(user=coach_user)
        grant = AccessGrantFactory(grantee_coach=coach, status=AccessGrant.Status.PENDING)
        response = post_json(
            client, f"/api/v1/access-grants/{grant.pk}/accept/", {}, **auth_headers(coach_user)
        )
        assert response.status_code == 200, response.data
        assert response.json()["status"] == AccessGrant.Status.ACTIVE
        event = AuditEvent.objects.get(action="access_grant.accepted")
        assert event.actor_id == coach_user.pk

    def test_non_beneficiary_404(self, client):
        grant = AccessGrantFactory()
        stranger = verified_user()
        response = post_json(
            client, f"/api/v1/access-grants/{grant.pk}/accept/", {}, **auth_headers(stranger)
        )
        assert response.status_code == 404

    def test_expired_grant_410(self, client):
        coach_user = verified_user()
        coach = CoachProfileFactory(user=coach_user)
        grant = AccessGrantFactory(
            grantee_coach=coach,
            status=AccessGrant.Status.PENDING,
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        response = post_json(
            client, f"/api/v1/access-grants/{grant.pk}/accept/", {}, **auth_headers(coach_user)
        )
        assert response.status_code == 410
        assert response.json()["error"]["code"] == "grant_expired"


class TestGrantRevoke:
    def test_anonymous_refused(self, client):
        grant = AccessGrantFactory()
        assert post_json(client, f"/api/v1/access-grants/{grant.pk}/revoke/", {}).status_code == 401

    def test_owner_revokes(self, client):
        owner = UserFactory()  # révocation : email vérifié non requis
        athlete = AthleteProfileFactory(user=owner)
        grant = AccessGrantFactory(athlete=athlete, granted_by=owner)
        response = post_json(
            client, f"/api/v1/access-grants/{grant.pk}/revoke/", {}, **auth_headers(owner)
        )
        assert response.status_code == 200, response.data
        body = response.json()
        assert body["status"] == AccessGrant.Status.REVOKED
        assert body["revoked_at"] is not None
        event = AuditEvent.objects.get(action="access_grant.revoked")
        assert event.actor_id == owner.pk

    def test_non_owner_cannot_revoke(self, client):
        grant = AccessGrantFactory()
        stranger = verified_user()
        response = post_json(
            client, f"/api/v1/access-grants/{grant.pk}/revoke/", {}, **auth_headers(stranger)
        )
        assert response.status_code == 403

    def test_team_grant_revoked_by_owner(self, client):
        owner = UserFactory()
        athlete = AthleteProfileFactory(user=owner)
        team = TeamFactory()
        grant = TeamAccessGrantFactory(athlete=athlete, granted_by=owner, grantee_team=team)
        response = post_json(
            client, f"/api/v1/access-grants/{grant.pk}/revoke/", {}, **auth_headers(owner)
        )
        assert response.status_code == 200
