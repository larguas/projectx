"""Tests du flux « device code » : émission, polling, approbation, révocation (feature 02)."""

import re
from datetime import timedelta

from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import DeviceAuthorization, generate_user_code, hash_code
from apps.accounts.tests.factories import DeviceAuthorizationFactory, UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json

CODE_URL = "/api/v1/auth/device/code/"
TOKEN_URL = "/api/v1/auth/device/token/"
APPROVE_URL = "/api/v1/auth/device/approve/"
CLIENTS_URL = "/api/v1/auth/clients/"
REFRESH_URL = "/api/v1/auth/refresh/"

USER_CODE_RE = re.compile(r"[A-HJ-KM-NP-Z2-9]{4}-[A-HJ-KM-NP-Z2-9]{4}")


def issue(client, client_type="pc_agent") -> tuple[dict, DeviceAuthorization]:
    """Émet un code d'autorisation ; retourne ``(réponse, autorisation en base)``."""
    response = post_json(client, CODE_URL, {"client_type": client_type})
    assert response.status_code == 201, response.data
    data = response.json()
    authorization = DeviceAuthorization.objects.get(device_code_hash=hash_code(data["device_code"]))
    return data, authorization


def poll(client, code: str) -> "object":
    """Polling du client en respectant l'intervalle (contourné côté base)."""
    authorization = DeviceAuthorization.objects.get(device_code_hash=hash_code(code))
    if authorization.last_polled_at is not None:
        authorization.last_polled_at = timezone.now() - timedelta(
            seconds=DeviceAuthorization.POLL_INTERVAL_SECONDS + 1
        )
        authorization.save(update_fields=["last_polled_at"])
    return post_json(client, TOKEN_URL, {"device_code": code})


def approve(client, user, user_code: str, approve: bool) -> "object":
    """Approbation / refus par l'utilisateur connecté."""
    return post_json(
        client, APPROVE_URL, {"user_code": user_code, "approve": approve}, **auth_headers(user)
    )


def error_code(response) -> str:
    return response.json()["error"]["code"]


class TestDeviceCodeIssuance:
    def test_issuance_returns_codes_and_metadata(self, client):
        data, _ = issue(client)
        assert USER_CODE_RE.fullmatch(data["user_code"])
        assert data["expires_in"] == int(DeviceAuthorization.CODE_TTL.total_seconds())
        assert data["interval"] == DeviceAuthorization.POLL_INTERVAL_SECONDS
        assert f"user_code={data['user_code']}" in data["verification_uri"]

    def test_codes_are_stored_hashed(self, client):
        data, authorization = issue(client)
        # Le code brut n'est jamais stocké : seul son haché SHA-256.
        assert authorization.device_code_hash == hash_code(data["device_code"])
        assert authorization.device_code_hash != data["device_code"]
        assert authorization.user_code_hash == hash_code(data["user_code"])
        assert authorization.status == DeviceAuthorization.Status.PENDING
        assert authorization.expires_at > timezone.now()

    def test_issuance_requires_valid_client_type(self, client):
        response = post_json(client, CODE_URL, {"client_type": "téléphone"})
        assert response.status_code == 400
        assert error_code(response) == "validation_error"

    def test_issuance_rejects_missing_client_type(self, client):
        response = post_json(client, CODE_URL, {})
        assert response.status_code == 400


class TestDeviceTokenPolling:
    def test_poll_before_approval_is_pending(self, client):
        data, _ = issue(client)
        response = poll(client, data["device_code"])
        assert response.status_code == 400
        assert error_code(response) == "authorization_pending"

    def test_rapid_polling_is_slowed_down(self, client):
        data, authorization = issue(client)
        assert poll(client, data["device_code"]).status_code == 400
        # Deuxième polling immédiat (sans respecter l'intervalle de 5 s).
        response = post_json(client, TOKEN_URL, {"device_code": data["device_code"]})
        assert response.status_code == 400
        assert error_code(response) == "slow_down"
        authorization.refresh_from_db()
        # Le slow_down ne compte pas comme tentative.
        assert authorization.poll_attempts == 1

    def test_unknown_device_code_is_invalid_grant(self, client):
        response = post_json(client, TOKEN_URL, {"device_code": "code-inconnu-xyz"})
        assert response.status_code == 400
        assert error_code(response) == "invalid_grant"

    def test_expired_authorization_is_rejected(self, client):
        device_code = "expired-device-code"
        DeviceAuthorizationFactory(
            device_code_hash=hash_code(device_code),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        response = poll(client, device_code)
        assert response.status_code == 400
        assert error_code(response) == "expired_token"
        authorization = DeviceAuthorization.objects.get(device_code_hash=hash_code(device_code))
        assert authorization.status == DeviceAuthorization.Status.EXPIRED

    def test_denied_authorization_is_rejected(self, client):
        user = UserFactory()
        data, _ = issue(client)
        approve(client, user, data["user_code"], approve=False)
        response = poll(client, data["device_code"])
        assert response.status_code == 400
        assert error_code(response) == "access_denied"

    def test_max_poll_attempts_expires_authorization(self, client):
        data, authorization = issue(client)
        max_attempts = DeviceAuthorization.MAX_POLL_ATTEMPTS
        for attempt in range(1, max_attempts + 2):
            response = poll(client, data["device_code"])
            if attempt <= max_attempts:
                assert error_code(response) == "authorization_pending", attempt
            else:
                assert error_code(response) == "expired_token", attempt
        authorization.refresh_from_db()
        assert authorization.status == DeviceAuthorization.Status.EXPIRED
        assert authorization.poll_attempts == max_attempts + 1


class TestDeviceApproval:
    def test_full_flow_grants_tokens(self, client):
        user = UserFactory()
        data, authorization = issue(client)

        response = approve(client, user, data["user_code"], approve=True)
        assert response.status_code == 200, response.data
        assert response.json() == {"status": "approved"}

        response = poll(client, data["device_code"])
        assert response.status_code == 200, response.data
        tokens = response.json()
        assert set(tokens) == {"access", "refresh"}

        # Les jetons portent les claims de révocabilité.
        access = AccessToken(tokens["access"])
        assert access["device_auth_id"] == str(authorization.id)
        assert access["client_type"] == DeviceAuthorization.ClientType.PC_AGENT

        authorization.refresh_from_db()
        assert authorization.status == DeviceAuthorization.Status.CONSUMED
        assert authorization.user == user

    def test_user_code_is_case_insensitive_and_stripped(self, client):
        user = UserFactory()
        data, _ = issue(client)
        response = approve(client, user, f"  {data['user_code'].lower()}  ", approve=True)
        assert response.status_code == 200

    def test_reused_device_code_is_invalid_grant(self, client):
        user = UserFactory()
        data, _ = issue(client)
        approve(client, user, data["user_code"], approve=True)
        assert poll(client, data["device_code"]).status_code == 200
        response = poll(client, data["device_code"])
        assert error_code(response) == "invalid_grant"

    def test_approve_unknown_user_code(self, client):
        user = UserFactory()
        response = approve(client, user, "AAAA-BBBB", approve=True)
        assert response.status_code == 400
        assert error_code(response) == "invalid_request"

    def test_double_approval_is_conflict(self, client):
        user = UserFactory()
        data, _ = issue(client)
        assert approve(client, user, data["user_code"], approve=True).status_code == 200
        response = approve(client, user, data["user_code"], approve=True)
        assert response.status_code == 409
        assert error_code(response) == "conflict"

    def test_approval_of_expired_code(self, client):
        user = UserFactory()
        user_code = generate_user_code()
        DeviceAuthorizationFactory(
            user_code_hash=hash_code(user_code),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        response = approve(client, user, user_code, approve=True)
        assert response.status_code == 400
        assert error_code(response) == "expired_token"

    def test_approval_requires_authentication(self, client):
        data, _ = issue(client)
        response = post_json(client, APPROVE_URL, {"user_code": data["user_code"], "approve": True})
        assert response.status_code == 401


class TestDeviceClients:
    def test_list_shows_only_own_clients(self, client):
        user = UserFactory()
        other = UserFactory()
        DeviceAuthorizationFactory(user=user)
        DeviceAuthorizationFactory(user=other)

        response = client.get(CLIENTS_URL, **auth_headers(user))
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["client_type"] == DeviceAuthorization.ClientType.PC_AGENT

    def test_revoke_denies_authorization_and_blocks_refresh(self, client):
        user = UserFactory()
        data, authorization = issue(client)
        approve(client, user, data["user_code"], approve=True)
        tokens = poll(client, data["device_code"]).json()

        response = client.delete(f"{CLIENTS_URL}{authorization.id}/", **auth_headers(user))
        assert response.status_code == 204
        authorization.refresh_from_db()
        assert authorization.status == DeviceAuthorization.Status.DENIED

        # Client révoqué : le renouvellement est refusé (critère d'acceptation).
        response = post_json(client, REFRESH_URL, {"refresh": tokens["refresh"]})
        assert response.status_code == 401
        assert error_code(response) == "client_revoked"

    def test_revoke_foreign_authorization_is_not_found(self, client):
        owner = UserFactory()
        stranger = UserFactory()
        authorization = DeviceAuthorizationFactory(user=owner)

        response = client.delete(f"{CLIENTS_URL}{authorization.id}/", **auth_headers(stranger))
        assert response.status_code == 404

    def test_revoke_requires_authentication(self, client):
        authorization = DeviceAuthorizationFactory()
        response = client.delete(f"{CLIENTS_URL}{authorization.id}/")
        assert response.status_code == 401
