"""Tests de throttling des endpoints sensibles (feature 02).

DRF lie ``SimpleRateThrottle.THROTTLE_RATES`` à l'objet dict des réglages au
moment de l'import : remplacer ``REST_FRAMEWORK`` via la fixture ``settings``
n'a donc aucun effet sur le throttle. On patche directement le dictionnaire
lu par la classe (``monkeypatch.setitem`` restaure la valeur après le test).
"""

from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.tests.factories import DEFAULT_TEST_PASSWORD, UserFactory
from apps.accounts.tests.helpers import post_json

LOGIN_URL = "/api/v1/auth/login/"
DEVICE_CODE_URL = "/api/v1/auth/device/code/"


def _with_rate(monkeypatch, scope: str, rate: str) -> None:
    """Abaisse le taux d'un scope pour la durée du test."""
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, scope, rate)


def test_login_is_throttled(client, monkeypatch):
    user = UserFactory()
    payload = {"email": user.email, "password": DEFAULT_TEST_PASSWORD}
    _with_rate(monkeypatch, "login", "1/minute")

    assert post_json(client, LOGIN_URL, payload).status_code == 200
    response = post_json(client, LOGIN_URL, payload)
    assert response.status_code == 429
    error = response.json()["error"]
    assert error["code"] == "rate_limited"


def test_device_code_is_throttled(client, monkeypatch):
    _with_rate(monkeypatch, "device_code", "2/minute")

    for _ in range(2):
        response = post_json(client, DEVICE_CODE_URL, {"client_type": "pc_agent"})
        assert response.status_code == 201, response.data
    response = post_json(client, DEVICE_CODE_URL, {"client_type": "pc_agent"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
