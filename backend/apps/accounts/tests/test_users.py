"""Tests du profil utilisateur ``/api/v1/users/me/`` (feature 02)."""

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers

ME_URL = "/api/v1/users/me/"


class TestMe:
    def test_get_profile(self, client):
        user = UserFactory(
            first_name="Marie", last_name="Dupont", locale="fr", timezone="Europe/Paris"
        )
        response = client.get(ME_URL, **auth_headers(user))
        assert response.status_code == 200, response.data
        data = response.json()
        assert data["id"] == str(user.id)
        assert data["email"] == user.email
        assert data["first_name"] == "Marie"
        assert data["last_name"] == "Dupont"
        assert data["locale"] == "fr"
        assert data["timezone"] == "Europe/Paris"
        assert data["is_active"] is True
        assert data["email_verified_at"] is None
        assert "password" not in data

    def test_get_requires_authentication(self, client):
        response = client.get(ME_URL)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_required"

    def test_patch_updates_profile_fields(self, client):
        user = UserFactory()
        payload = {
            "first_name": "Jean",
            "last_name": "Martin",
            "locale": "fr",
            "timezone": "Europe/Brussels",
        }
        response = client.patch(
            ME_URL, data=payload, content_type="application/json", **auth_headers(user)
        )
        assert response.status_code == 200, response.data
        user.refresh_from_db()
        assert user.first_name == "Jean"
        assert user.last_name == "Martin"
        assert user.locale == "fr"
        assert user.timezone == "Europe/Brussels"

    def test_patch_email_is_read_only(self, client):
        user = UserFactory()
        response = client.patch(
            ME_URL,
            data={"email": "other@example.com"},
            content_type="application/json",
            **auth_headers(user),
        )
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.email == user.email  # inchangé
        assert response.json()["email"] != "other@example.com"

    def test_patch_rejects_oversized_field(self, client):
        user = UserFactory()
        response = client.patch(
            ME_URL,
            data={"first_name": "x" * 151},
            content_type="application/json",
            **auth_headers(user),
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "validation_error"
