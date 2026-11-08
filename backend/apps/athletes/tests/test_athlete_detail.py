"""Tests de l'API sportif : ``GET/PATCH /api/v1/athletes/{id}/``.

Le détail est visible selon ``core.access.can_see_athlete`` (404 sinon,
l'existence n'est pas révélée) ; la mise à jour est réservée au propriétaire.
L'email n'apparaît que pour le propriétaire (``email: null`` sinon).
"""

import json

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.teams.tests.factories import AccessGrantFactory

SCOPE = "sessions:read"


def patch_json(client, url: str, payload: dict, **extra):
    """PATCH JSON via le client de test Django (``**extra`` : en-têtes HTTP)."""
    return client.patch(url, data=json.dumps(payload), content_type="application/json", **extra)


class TestAthleteDetailRead:
    def test_anonymous_refused(self, client):
        profile = AthleteProfileFactory()
        response = client.get(f"/api/v1/athletes/{profile.pk}/")
        assert response.status_code == 401

    def test_owner_sees_own_profile_with_email(self, client):
        owner = UserFactory(email="sportif@example.com")
        profile = AthleteProfileFactory(user=owner)
        response = client.get(f"/api/v1/athletes/{profile.pk}/", **auth_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "sportif@example.com"

    def test_coach_with_grant_sees_profile_without_email(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete = AthleteProfileFactory(user=UserFactory(email="secret@example.com"))
        AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=[SCOPE])
        response = client.get(f"/api/v1/athletes/{athlete.pk}/", **auth_headers(coach_user))
        assert response.status_code == 200
        body = response.json()
        assert body["email"] is None

    def test_coach_without_grant_gets_404(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        athlete = AthleteProfileFactory()
        response = client.get(f"/api/v1/athletes/{athlete.pk}/", **auth_headers(coach_user))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_revoked_grant_gets_404(self, client):
        from apps.teams.models import AccessGrant

        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete = AthleteProfileFactory()
        AccessGrantFactory(athlete=athlete, grantee_coach=coach, status=AccessGrant.Status.REVOKED)
        response = client.get(f"/api/v1/athletes/{athlete.pk}/", **auth_headers(coach_user))
        assert response.status_code == 404

    def test_unknown_id_gets_404(self, client):
        owner = UserFactory()
        response = client.get(f"/api/v1/athletes/{UserFactory().pk}/", **auth_headers(owner))
        assert response.status_code == 404

    def test_coach_read_emits_audit_event(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete = AthleteProfileFactory()
        AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=[SCOPE])
        client.get(f"/api/v1/athletes/{athlete.pk}/", **auth_headers(coach_user))
        event = AuditEvent.objects.get(action="athlete.viewed")
        assert event.actor_id == coach_user.pk
        assert event.athlete_id == athlete.pk

    def test_owner_read_no_audit_event(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        client.get(f"/api/v1/athletes/{profile.pk}/", **auth_headers(owner))
        assert not AuditEvent.objects.filter(action="athlete.viewed").exists()


class TestAthleteDetailUpdate:
    def test_owner_updates_own_profile(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        response = patch_json(
            client,
            f"/api/v1/athletes/{profile.pk}/",
            {"sport": "Triathlon", "height_cm": 175},
            **auth_headers(owner),
        )
        assert response.status_code == 200, response.data
        profile.refresh_from_db()
        assert profile.sport == "Triathlon"
        assert profile.height_cm == 175

    def test_coach_cannot_update(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete = AthleteProfileFactory()
        AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=[SCOPE])
        response = patch_json(
            client,
            f"/api/v1/athletes/{athlete.pk}/",
            {"sport": "Hacking"},
            **auth_headers(coach_user),
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_stranger_cannot_update(self, client):
        profile = AthleteProfileFactory()
        stranger = UserFactory()
        response = patch_json(
            client,
            f"/api/v1/athletes/{profile.pk}/",
            {"sport": "Hacking"},
            **auth_headers(stranger),
        )
        assert response.status_code == 404

    def test_anonymous_cannot_update(self, client):
        profile = AthleteProfileFactory()
        response = patch_json(client, f"/api/v1/athletes/{profile.pk}/", {"sport": "X"})
        assert response.status_code == 401
