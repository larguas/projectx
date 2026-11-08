"""Tests des flux de mots de passe : oublié, réinitialisation, changement (feature 02)."""

from datetime import datetime, timedelta

from django.core import mail

from apps.accounts.tests.factories import DEFAULT_TEST_PASSWORD, UserFactory
from apps.accounts.tests.helpers import auth_headers, login_tokens, post_json, token_from_link

FORGOT_URL = "/api/v1/auth/password/forgot/"
RESET_URL = "/api/v1/auth/password/reset/"
CHANGE_URL = "/api/v1/auth/password/change/"
LOGIN_URL = "/api/v1/auth/login/"

NEW_PASSWORD = "Nouveau-MotDePasse42"


def _request_reset(client, email: str) -> dict:
    """Demande de réinitialisation ; retourne les paramètres du lien d'email."""
    response = post_json(client, FORGOT_URL, {"email": email})
    assert response.status_code == 200, response.data
    assert "message" in response.json()
    return token_from_link(mail.outbox[-1].body)


class TestPasswordForgot:
    def test_forgot_sends_email_for_known_user(self, client):
        user = UserFactory()
        params = _request_reset(client, user.email.upper())
        assert "uid" in params and "token" in params
        assert mail.outbox[-1].to == [user.email]

    def test_forgot_does_not_reveal_unknown_email(self, client):
        response = post_json(client, FORGOT_URL, {"email": "ghost@example.com"})
        assert response.status_code == 200
        # Même message que pour un compte existant, et aucun email envoyé.
        assert response.json()["message"]
        assert len(mail.outbox) == 0

    def test_forgot_rejects_invalid_email(self, client):
        response = post_json(client, FORGOT_URL, {"email": "pas-un-email"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "validation_error"


class TestPasswordReset:
    def test_reset_with_valid_token(self, client):
        user = UserFactory()
        params = _request_reset(client, user.email)

        response = post_json(client, RESET_URL, {**params, "new_password": NEW_PASSWORD})
        assert response.status_code == 200, response.data
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD)
        # L'ancien mot de passe ne fonctionne plus.
        assert (
            post_json(
                client, LOGIN_URL, {"email": user.email, "password": DEFAULT_TEST_PASSWORD}
            ).status_code
            == 401
        )
        access, _ = login_tokens(client, user.email, NEW_PASSWORD)
        assert access

    def test_reset_token_is_single_use(self, client):
        user = UserFactory()
        params = _request_reset(client, user.email)
        payload = {**params, "new_password": NEW_PASSWORD}

        assert post_json(client, RESET_URL, payload).status_code == 200
        # Le jeton est invalidé par le changement de mot de passe.
        response = post_json(client, RESET_URL, payload)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_reset_token"

    def test_reset_rejects_tampered_token(self, client):
        user = UserFactory()
        params = _request_reset(client, user.email)
        params["token"] = params["token"][:-4] + "zzzz"

        response = post_json(client, RESET_URL, {**params, "new_password": NEW_PASSWORD})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_reset_token"

    def test_reset_rejects_expired_token(self, client, monkeypatch):
        user = UserFactory()
        params = _request_reset(client, user.email)
        # Décale l'horloge du générateur de 2 h (> timeout de 1 h par défaut).
        from apps.accounts.services import _reset_token_generator

        monkeypatch.setattr(
            _reset_token_generator,
            "_now",
            lambda: datetime.now() + timedelta(hours=2),
        )

        response = post_json(client, RESET_URL, {**params, "new_password": NEW_PASSWORD})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_reset_token"
        user.refresh_from_db()
        assert user.check_password(DEFAULT_TEST_PASSWORD)

    def test_reset_rejects_unknown_uid(self, client):
        response = post_json(
            client, RESET_URL, {"uid": "aaaa", "token": "abc", "new_password": NEW_PASSWORD}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_reset_token"

    def test_reset_rejects_weak_new_password(self, client):
        user = UserFactory()
        params = _request_reset(client, user.email)
        response = post_json(client, RESET_URL, {**params, "new_password": "court"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "validation_error"


class TestPasswordChange:
    def test_change_with_correct_old_password(self, client):
        user = UserFactory()
        response = client.post(
            CHANGE_URL,
            data={"old_password": DEFAULT_TEST_PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **auth_headers(user),
        )
        assert response.status_code == 200, response.data
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD)

    def test_change_rejects_wrong_old_password(self, client):
        user = UserFactory()
        response = client.post(
            CHANGE_URL,
            data={"old_password": "Ancien-Faux-MotDePasse", "new_password": NEW_PASSWORD},
            content_type="application/json",
            **auth_headers(user),
        )
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert "old_password" in error["details"]

    def test_change_rejects_weak_new_password(self, client):
        user = UserFactory()
        response = client.post(
            CHANGE_URL,
            data={"old_password": DEFAULT_TEST_PASSWORD, "new_password": "1234567890a"},
            content_type="application/json",
            **auth_headers(user),
        )
        assert response.status_code == 400

    def test_change_requires_authentication(self, client):
        response = post_json(
            client, CHANGE_URL, {"old_password": "x", "new_password": NEW_PASSWORD}
        )
        assert response.status_code == 401
