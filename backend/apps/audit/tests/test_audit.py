"""Tests de l'app d'audit minimale (``apps.audit``).

Garanties : insertion seule au niveau du modèle ; ``record_event`` ne casse
jamais l'opération métier (échec d'écriture -> log + ``None``) ; extraction
IP / user agent depuis la requête.
"""

import pytest
from django.test import RequestFactory

from apps.accounts.tests.factories import UserFactory
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditError, AuditEvent
from apps.audit.services import record_event


class TestAuditEventImmutability:
    def test_insert_allowed(self):
        actor = UserFactory()
        event = AuditEvent.objects.create(actor=actor, action="test.action")
        assert event.pk is not None
        assert event.created_at is not None

    def test_save_after_persist_refused(self):
        actor = UserFactory()
        event = AuditEvent.objects.create(actor=actor, action="test.action")
        event.action = "test.other"
        with pytest.raises(AuditError):
            event.save()

    def test_delete_refused(self):
        actor = UserFactory()
        event = AuditEvent.objects.create(actor=actor, action="test.action")
        with pytest.raises(AuditError):
            event.delete()


class TestRecordEvent:
    def test_creates_event_with_target_and_athlete(self):
        actor = UserFactory()
        athlete = AthleteProfileFactory()
        event = record_event(actor, "athlete.viewed", athlete, athlete=athlete)
        assert event is not None
        assert event.actor_id == actor.pk
        assert event.action == "athlete.viewed"
        assert event.target_type == "AthleteProfile"
        assert event.target_id == athlete.pk
        assert event.athlete_id == athlete.pk

    def test_event_without_target(self):
        actor = UserFactory()
        event = record_event(actor, "team.created", None)
        assert event is not None
        assert event.target_type == ""
        assert event.target_id is None
        assert event.athlete is None

    def test_metadata_stored(self):
        actor = UserFactory()
        event = record_event(actor, "athlete.listed", None, metadata={"granted_athletes": 3})
        assert event.metadata == {"granted_athletes": 3}

    def test_default_metadata_empty_dict(self):
        actor = UserFactory()
        event = record_event(actor, "x.y", None)
        assert event.metadata == {}

    def test_request_extracts_ip_and_user_agent(self):
        actor = UserFactory()
        request = RequestFactory().get(
            "/x/", HTTP_USER_AGENT="pytest-agent", REMOTE_ADDR="10.1.2.3"
        )
        event = record_event(actor, "x.y", None, request=request)
        assert event.ip == "10.1.2.3"
        assert event.user_agent == "pytest-agent"

    def test_x_forwarded_for_takes_precedence(self):
        actor = UserFactory()
        request = RequestFactory().get("/x/", HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1")
        event = record_event(actor, "x.y", None, request=request)
        assert event.ip == "203.0.113.7"

    def test_no_request_gives_null_ip(self):
        actor = UserFactory()
        event = record_event(actor, "x.y", None)
        assert event.ip is None
        assert event.user_agent == ""

    def test_write_failure_returns_none_and_does_not_raise(self, monkeypatch):
        from apps.audit import models as audit_models

        def boom(*args, **kwargs):
            raise RuntimeError("base de données indisponible")

        monkeypatch.setattr(audit_models.AuditEvent, "save", boom)
        actor = UserFactory()
        assert record_event(actor, "x.y", None) is None
