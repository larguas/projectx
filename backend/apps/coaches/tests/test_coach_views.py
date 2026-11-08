"""Tests de l'API coachs : annuaire, création à la demande, détail/mise à jour.

L'annuaire est ouvert à tout utilisateur authentifié (pas de grant requis) ;
l'email n'est jamais exposé.
"""

import json

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.coaches.models import CoachProfile
from apps.coaches.tests.factories import CoachProfileFactory


def patch_json(client, url: str, payload: dict, **extra):
    return client.patch(url, data=json.dumps(payload), content_type="application/json", **extra)


class TestCoachDirectory:
    def test_anonymous_refused(self, client):
        response = client.get("/api/v1/coaches/")
        assert response.status_code == 401

    def test_any_authenticated_user_can_browse(self, client):
        user = UserFactory()
        CoachProfileFactory(organization_name="Club Alpin")
        response = client.get("/api/v1/coaches/", **auth_headers(user))
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert "email" not in results[0]

    def test_filter_by_organization_case_insensitive(self, client):
        user = UserFactory()
        matching = CoachProfileFactory(organization_name="Club Alpin")
        CoachProfileFactory(organization_name="Élite Paris")
        response = client.get("/api/v1/coaches/?organization_name=alpin", **auth_headers(user))
        assert [c["id"] for c in response.json()["results"]] == [str(matching.pk)]


class TestCreateCoachProfile:
    def test_creates_own_profile(self, client):
        user = UserFactory()
        payload = {"organization_name": "Club Alpin", "bio": "10 ans d'expérience"}
        response = post_json(client, "/api/v1/coaches/", payload, **auth_headers(user))
        assert response.status_code == 201, response.data
        body = response.json()
        assert body["organization_name"] == "Club Alpin"
        assert "email" not in body
        assert CoachProfile.objects.filter(user=user).exists()

    def test_second_creation_conflict(self, client):
        user = UserFactory()
        post_json(client, "/api/v1/coaches/", {}, **auth_headers(user))
        response = post_json(client, "/api/v1/coaches/", {}, **auth_headers(user))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_anonymous_cannot_create(self, client):
        response = post_json(client, "/api/v1/coaches/", {})
        assert response.status_code == 401


class TestCoachDetail:
    def test_any_authenticated_user_can_read(self, client):
        user = UserFactory()
        profile = CoachProfileFactory(organization_name="Club Alpin")
        response = client.get(f"/api/v1/coaches/{profile.pk}/", **auth_headers(user))
        assert response.status_code == 200
        assert response.json()["organization_name"] == "Club Alpin"

    def test_unknown_id_404(self, client):
        user = UserFactory()
        response = client.get(f"/api/v1/coaches/{UserFactory().pk}/", **auth_headers(user))
        assert response.status_code == 404

    def test_owner_updates_own_profile(self, client):
        owner = UserFactory()
        profile = CoachProfileFactory(user=owner)
        response = patch_json(
            client, f"/api/v1/coaches/{profile.pk}/", {"bio": "nouveau bio"}, **auth_headers(owner)
        )
        assert response.status_code == 200, response.data
        profile.refresh_from_db()
        assert profile.bio == "nouveau bio"

    def test_non_owner_cannot_update(self, client):
        profile = CoachProfileFactory()
        stranger = UserFactory()
        response = patch_json(
            client, f"/api/v1/coaches/{profile.pk}/", {"bio": "piratage"}, **auth_headers(stranger)
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_anonymous_cannot_update(self, client):
        profile = CoachProfileFactory()
        response = patch_json(client, f"/api/v1/coaches/{profile.pk}/", {"bio": "x"})
        assert response.status_code == 401
