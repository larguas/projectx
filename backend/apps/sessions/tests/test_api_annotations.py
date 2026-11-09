"""Tests des annotations : ``/api/v1/sessions/{id}/annotations/`` (+ détail).

CRUD avec tri par ``offset_ms`` ; création/modification autorisées pendant
``recording`` et après ``completed``, jamais sur ``created`` / ``cancelled`` /
``failed`` (``annotation_blocked``, 409) ; droits : lecture = ``sessions:read``
(traçée pour un non-propriétaire), écriture = ``sessions:write``.
"""

import json

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.sessions.models import SessionAnnotation
from apps.sessions.tests.factories import make_session
from apps.teams.tests.factories import AccessGrantFactory


def _list_url(session):
    return f"/api/v1/sessions/{session.pk}/annotations/"


def _detail_url(session, annotation):
    return f"/api/v1/sessions/{session.pk}/annotations/{annotation.pk}/"


def _patch(client, user, session, annotation, payload):
    return client.patch(
        _detail_url(session, annotation),
        data=json.dumps(payload),
        content_type="application/json",
        **auth_headers(user),
    )


def _coach_with_grant(athlete, scopes):
    coach_user = UserFactory()
    coach = CoachProfileFactory(user=coach_user)
    AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=scopes)
    return coach_user


class TestAnnotationCreate:
    def test_create_during_recording(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="recording")
        payload = {"kind": "set_start", "offset_ms": 1200, "text": "série 1"}
        response = post_json(client, _list_url(session), payload, **auth_headers(owner))
        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "set_start"
        assert body["offset_ms"] == 1200
        assert "author" not in body  # l'auteur n'est jamais exposé

    def test_create_after_completed(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="completed")
        response = post_json(
            client, _list_url(session), {"kind": "note", "offset_ms": 0}, **auth_headers(owner)
        )
        assert response.status_code == 201

    def test_create_on_created_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile)
        response = post_json(
            client, _list_url(session), {"kind": "note", "offset_ms": 0}, **auth_headers(owner)
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "annotation_blocked"

    def test_create_on_cancelled_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="cancelled")
        response = post_json(
            client, _list_url(session), {"kind": "note", "offset_ms": 0}, **auth_headers(owner)
        )
        assert response.status_code == 409

    def test_create_on_failed_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="failed")
        response = post_json(
            client, _list_url(session), {"kind": "note", "offset_ms": 0}, **auth_headers(owner)
        )
        assert response.status_code == 409

    def test_invalid_kind_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="recording")
        response = post_json(
            client, _list_url(session), {"kind": "bogus", "offset_ms": 0}, **auth_headers(owner)
        )
        assert response.status_code == 400

    def test_read_only_coach_cannot_create(self, client):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status="recording")
        coach_user = _coach_with_grant(profile, ["sessions:read"])
        response = post_json(
            client, _list_url(session), {"kind": "note", "offset_ms": 0}, **auth_headers(coach_user)
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_anonymous_refused(self, client):
        session = make_session(status="recording")
        assert (
            post_json(client, _list_url(session), {"kind": "note", "offset_ms": 0}).status_code
            == 401
        )


class TestAnnotationList:
    def test_list_sorted_by_offset(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="recording")
        SessionAnnotation.objects.create(session=session, kind="note", offset_ms=3000, author=owner)
        SessionAnnotation.objects.create(session=session, kind="note", offset_ms=1000, author=owner)
        response = client.get(_list_url(session), **auth_headers(owner))
        assert response.status_code == 200
        assert [a["offset_ms"] for a in response.json()["results"]] == [1000, 3000]

    def test_coach_read_is_audited(self, client):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status="recording")
        coach_user = _coach_with_grant(profile, ["sessions:read"])
        response = client.get(_list_url(session), **auth_headers(coach_user))
        assert response.status_code == 200
        event = AuditEvent.objects.get(action="session.viewed")
        assert event.actor_id == coach_user.pk


class TestAnnotationUpdateDelete:
    def _setup(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="recording")
        annotation = SessionAnnotation.objects.create(
            session=session, kind="set_start", offset_ms=100, author=owner
        )
        return owner, session, annotation

    def test_patch_fields(self, client):
        owner, session, annotation = self._setup(client)
        response = _patch(
            client,
            owner,
            session,
            annotation,
            {"kind": "set_end", "offset_ms": 250, "text": "corrigé"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "set_end"
        assert body["offset_ms"] == 250

    def test_patch_session_field_ignored(self, client):
        owner, session, annotation = self._setup(client)
        other = make_session(status="recording")
        response = _patch(client, owner, session, annotation, {"session": str(other.pk)})
        assert response.status_code == 200  # champ inconnu : ignoré
        annotation.refresh_from_db()
        assert annotation.session_id == session.pk

    def test_patch_on_cancelled_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="cancelled")
        annotation = SessionAnnotation.objects.create(
            session=session, kind="note", offset_ms=0, author=owner
        )
        response = _patch(client, owner, session, annotation, {"text": "non"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "annotation_blocked"

    def test_delete(self, client):
        owner, session, annotation = self._setup(client)
        response = client.delete(_detail_url(session, annotation), **auth_headers(owner))
        assert response.status_code == 204
        assert not SessionAnnotation.objects.filter(pk=annotation.pk).exists()

    def test_unknown_annotation_404(self, client):
        owner, session, _annotation = self._setup(client)
        missing = make_session(status="recording")
        fake = SessionAnnotation.objects.create(
            session=missing, kind="note", offset_ms=0, author=owner
        )
        # L'annotation appartient à une autre séance : invisible pour ``owner``.
        response = client.get(_detail_url(session, fake), **auth_headers(owner))
        assert response.status_code == 404
