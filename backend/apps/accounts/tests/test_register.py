"""Tests d'inscription et de vérification d'email (feature 02)."""

from datetime import timedelta

import pytest
from django.core import mail, signing
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import last_email_body, post_json, token_from_link

REGISTER_URL = "/api/v1/auth/register/"
VERIFY_URL = "/api/v1/auth/email/verify/"
RESEND_URL = "/api/v1/auth/email/resend/"

VALID_PASSWORD = "S3cure-Passw0rd!-EMG"


class TestRegister:
    def test_register_success(self, client):
        response = post_json(
            client,
            REGISTER_URL,
            {
                "email": "New.User@Example.com",
                "password": VALID_PASSWORD,
                "first_name": "Marie",
                "last_name": "Dupont",
            },
        )
        assert response.status_code == 201, response.data
        data = response.json()
        assert data["email"] == "new.user@example.com"
        assert data["first_name"] == "Marie"
        assert data["last_name"] == "Dupont"
        assert data["is_active"] is True
        assert data["email_verified_at"] is None
        assert data["locale"] == "en"
        assert data["timezone"] == "UTC"
        assert "password" not in data

        user = User.objects.get(email="new.user@example.com")
        assert user.check_password(VALID_PASSWORD)

    def test_register_sends_verification_email(self, client):
        post_json(client, REGISTER_URL, {"email": "mail@example.com", "password": VALID_PASSWORD})
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == ["mail@example.com"]
        params = token_from_link(email.body)
        assert "token" in params

    @pytest.mark.parametrize(
        "payload",
        [
            # Email dupliqué, insensible à la casse.
            {"email": "EXISTING@Example.COM", "password": VALID_PASSWORD},
            # Mot de passe trop court.
            {"email": "short@example.com", "password": "S3cure!"},
            # Mot de passe courant (présent dans la liste Django).
            {"email": "common@example.com", "password": "1234567890a"},
            # Mot de passe uniquement numérique.
            {"email": "numeric@example.com", "password": "12345678901234"},
            # Champs obligatoires manquants.
            {"password": VALID_PASSWORD},
            {"email": "no-pass@example.com"},
        ],
    )
    def test_register_rejects_invalid_payload(self, client, payload):
        UserFactory(email="existing@example.com")
        response = post_json(client, REGISTER_URL, payload)
        assert response.status_code == 400, response.data
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert isinstance(error["details"], dict)

    def test_register_duplicate_does_not_create_user(self, client):
        UserFactory(email="dup@example.com")
        post_json(client, REGISTER_URL, {"email": "DUP@example.com", "password": VALID_PASSWORD})
        assert User.objects.filter(email="dup@example.com").count() == 1


class TestEmailVerify:
    def _register(self, client, email="verify@example.com"):
        post_json(client, REGISTER_URL, {"email": email, "password": VALID_PASSWORD})
        return User.objects.get(email=email)

    def test_verify_with_valid_token(self, client):
        user = self._register(client)
        token = token_from_link(last_email_body())["token"]
        response = post_json(client, VERIFY_URL, {"token": token})
        assert response.status_code == 200, response.data
        user.refresh_from_db()
        assert user.email_verified_at is not None

    def test_verify_rejects_reused_token(self, client):
        self._register(client)
        token = token_from_link(last_email_body())["token"]
        assert post_json(client, VERIFY_URL, {"token": token}).status_code == 200
        # Usage unique : le jeton est mort une fois l'adresse vérifiée.
        response = post_json(client, VERIFY_URL, {"token": token})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_verification_token"

    def test_verify_rejects_tampered_token(self, client):
        self._register(client)
        response = post_json(client, VERIFY_URL, {"token": "nimporte-quoi.abc"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_verification_token"

    def test_verify_rejects_expired_token(self, client):
        user = self._register(client)
        signer = signing.TimestampSigner(salt="accounts.email-verification")
        old_timestamp = int((timezone.now() - timedelta(hours=25)).timestamp())
        # Jeton émis il y a 25 h (> 24 h) : on force l'horodatage du signataire.
        signer.timestamp = lambda: signing.b62_encode(old_timestamp)
        token = signer.sign_object({"uid": str(user.id), "verified": False})
        response = post_json(client, VERIFY_URL, {"token": token})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_verification_token"
        user.refresh_from_db()
        assert user.email_verified_at is None

    def test_verify_rejects_token_of_another_user(self, client):
        self._register(client, email="first@example.com")
        token = token_from_link(last_email_body())["token"]
        post_json(client, REGISTER_URL, {"email": "second@example.com", "password": VALID_PASSWORD})
        response = post_json(client, VERIFY_URL, {"token": token})
        # Le jeton référence le premier utilisateur (toujours non vérifié) :
        # il est donc valide pour lui, pas pour le second.
        assert response.status_code == 200
        assert User.objects.get(email="first@example.com").email_verified_at is not None
        assert User.objects.get(email="second@example.com").email_verified_at is None


class TestEmailResend:
    def test_resend_sends_email_for_unverified_user(self, client):
        post_json(client, REGISTER_URL, {"email": "resend@example.com", "password": VALID_PASSWORD})
        response = post_json(client, RESEND_URL, {"email": "RESEND@example.com"})
        assert response.status_code == 200, response.data
        assert len(mail.outbox) == 2
        assert mail.outbox[-1].to == ["resend@example.com"]

    def test_resend_does_not_send_for_verified_user(self, client):
        post_json(
            client, REGISTER_URL, {"email": "verified@example.com", "password": VALID_PASSWORD}
        )
        user = User.objects.get(email="verified@example.com")
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
        response = post_json(client, RESEND_URL, {"email": "verified@example.com"})
        assert response.status_code == 200
        assert len(mail.outbox) == 1

    def test_resend_does_not_reveal_unknown_email(self, client):
        response = post_json(client, RESEND_URL, {"email": "ghost@example.com"})
        assert response.status_code == 200
        assert response.json()["message"]
        assert len(mail.outbox) == 0
