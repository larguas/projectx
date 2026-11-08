"""Tests du handler d'exceptions DRF : format d'erreur unique."""

from django.db import IntegrityError
from django.test import RequestFactory
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.exceptions import drf_exception_handler


def _context(path="/api/v1/thing/"):
    return {"request": RequestFactory().get(path)}


def test_validation_error_format():
    exc = ValidationError({"email": ["Ce champ est obligatoire."], "age": ["Doit être positif."]})
    response = drf_exception_handler(exc, _context())
    assert response.status_code == 400
    error = response.data["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == "validation_error"
    assert error["details"]["email"] == ["Ce champ est obligatoire."]


def test_not_found_format():
    response = drf_exception_handler(NotFound(), _context())
    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_permission_denied_format():
    response = drf_exception_handler(PermissionDenied(), _context())
    assert response.status_code == 403
    assert response.data["error"]["code"] == "permission_denied"


def test_integrity_error_becomes_conflict():
    response = drf_exception_handler(IntegrityError("duplicate key value"), _context())
    assert response.status_code == 409
    assert response.data["error"]["code"] == "conflict"


def test_unhandled_exception_becomes_500():
    response = drf_exception_handler(ValueError("boom"), _context())
    assert response.status_code == 500
    error = response.data["error"]
    assert error["code"] == "server_error"
    # Le détail interne ne fuite jamais dans la réponse.
    assert "boom" not in str(error)
