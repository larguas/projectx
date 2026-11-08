"""Tests de connexion, renouvellement (rotation) et déconnexion (feature 02)."""

from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.tests.factories import DEFAULT_TEST_PASSWORD, UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json

LOGIN_URL = "/api/v1/auth/login/"
REFRESH_URL = "/api/v1/auth/refresh/"
LOGOUT_URL = "/api/v1/auth/logout/"


def _login(client, user) -> dict:
    response = post_json(
        client,
        LOGIN_URL,
        {"email": user.email, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.data
    return response.json()


class TestLogin:
    def test_login_success(self, client):
        user = UserFactory()
        # L'email est insensible à la casse.
        response = post_json(
            client, LOGIN_URL, {"email": user.email.upper(), "password": DEFAULT_TEST_PASSWORD}
        )
        assert response.status_code == 200, response.data
        data = response.json()
        assert set(data) == {"access", "refresh"}

        access = AccessToken(data["access"])
        # Claim simplejwt par défaut : l'identifiant utilisateur.
        assert access["user_id"] == str(user.id)

    def test_login_rejects_wrong_password(self, client):
        UserFactory()
        response = post_json(
            client, LOGIN_URL, {"email": "user0@example.com", "password": "Mauvais-MotDePasse1"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_required"

    def test_login_rejects_unknown_email(self, client):
        response = post_json(
            client, LOGIN_URL, {"email": "ghost@example.com", "password": DEFAULT_TEST_PASSWORD}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_required"

    def test_login_rejects_inactive_user(self, client):
        UserFactory(is_active=False)
        response = post_json(
            client, LOGIN_URL, {"email": "user0@example.com", "password": DEFAULT_TEST_PASSWORD}
        )
        assert response.status_code == 401

    def test_login_rejects_missing_fields(self, client):
        response = post_json(client, LOGIN_URL, {})
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert set(error["details"]) == {"email", "password"}


class TestRefresh:
    def test_refresh_rotates_and_blacklists_old_token(self, client):
        user = UserFactory()
        tokens = _login(client, user)

        response = post_json(client, REFRESH_URL, {"refresh": tokens["refresh"]})
        assert response.status_code == 200, response.data
        new_tokens = response.json()
        assert new_tokens["access"] != tokens["access"]

        # Rotation : l'ancien refresh est blacklisté et inutilisable.
        response = post_json(client, REFRESH_URL, {"refresh": tokens["refresh"]})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_required"

    def test_refresh_rejects_garbage_token(self, client):
        response = post_json(client, REFRESH_URL, {"refresh": "abc.def.ghi"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_required"

    def test_refresh_rejects_access_token(self, client):
        user = UserFactory()
        tokens = _login(client, user)
        # Un access token n'est pas un refresh token.
        response = post_json(client, REFRESH_URL, {"refresh": tokens["access"]})
        assert response.status_code == 401

    def test_refresh_rejects_missing_field(self, client):
        response = post_json(client, REFRESH_URL, {})
        assert response.status_code == 400


class TestLogout:
    def test_logout_blacklists_refresh_token(self, client):
        user = UserFactory()
        tokens = _login(client, user)

        response = client.post(
            LOGOUT_URL, data={"refresh": tokens["refresh"]}, **auth_headers(user)
        )
        assert response.status_code == 204

        # Le refresh blacklisted ne peut plus être utilisé.
        response = post_json(client, REFRESH_URL, {"refresh": tokens["refresh"]})
        assert response.status_code == 401

    def test_logout_requires_authentication(self, client):
        response = post_json(client, LOGOUT_URL, {"refresh": "x"})
        assert response.status_code == 401

    def test_logout_rejects_invalid_refresh(self, client):
        user = UserFactory()
        response = client.post(LOGOUT_URL, data={"refresh": "invalide"}, **auth_headers(user))
        assert response.status_code == 401
