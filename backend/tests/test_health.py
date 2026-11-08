"""Tests de l'endpoint de santé ``GET /api/v1/health/``."""

import pytest


@pytest.mark.django_db
def test_health_ok(client, monkeypatch):
    # Redis est simulé : la vérification réelle passe par le client Redis.
    monkeypatch.setattr("core.health.check_redis", lambda: "ok")
    response = client.get("/api/v1/health/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"app": "ok", "database": "ok", "redis": "ok"}


@pytest.mark.django_db
def test_health_degraded_when_redis_down(client, monkeypatch):
    monkeypatch.setattr("core.health.check_redis", lambda: "error")
    response = client.get("/api/v1/health/")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["redis"] == "error"
    assert body["checks"]["database"] == "ok"


@pytest.mark.django_db
def test_health_degraded_when_database_down(client, monkeypatch):
    monkeypatch.setattr("core.health.check_redis", lambda: "ok")
    monkeypatch.setattr("core.health.check_database", lambda: "error")
    response = client.get("/api/v1/health/")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "error"


@pytest.mark.django_db
def test_health_propagates_request_id(client, monkeypatch):
    """L'identifiant de requête entrant est renvoyé et propagé aux logs."""
    monkeypatch.setattr("core.health.check_redis", lambda: "ok")
    response = client.get("/api/v1/health/", HTTP_X_REQUEST_ID="req-test-123")
    assert response["X-Request-ID"] == "req-test-123"


@pytest.mark.django_db
def test_health_generates_request_id_when_missing(client, monkeypatch):
    monkeypatch.setattr("core.health.check_redis", lambda: "ok")
    response = client.get("/api/v1/health/")
    assert response["X-Request-ID"]
    assert response["X-Request-ID"] != "req-test-123"
