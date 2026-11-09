"""Tests des services d'annotations de la feature 06.

Règle métier : les annotations sont autorisées PENDANT ``recording`` et APRÈS
``completed`` (corrections du coach), JAMAIS sur ``created`` / ``cancelled`` /
``failed`` (``annotation_blocked``, 409). L'auteur est l'utilisateur qui agit
(jamais modifiable par l'API) ; ``session`` non modifiable.
"""

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.sessions import services
from apps.sessions.models import Session, SessionAnnotation
from apps.sessions.tests.factories import make_session
from apps.teams.tests.factories import AccessGrantFactory

from .helpers import SCOPE_WRITE


def _annotation_data(**overrides):
    data = {"kind": "set_start", "offset_ms": 1500, "text": "", "metadata": {}}
    data.update(overrides)
    return data


def _error_code(fn, *args):
    with pytest.raises(services.SessionsServiceError) as excinfo:
        fn(*args)
    return excinfo.value.code


class TestCreateAnnotation:
    @pytest.mark.parametrize("status", ["recording", "completed"])
    def test_allowed_during_recording_and_after_completed(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)

        annotation = services.create_annotation(profile.user, str(session.pk), _annotation_data())

        assert annotation.session_id == session.pk
        assert annotation.author_id == profile.user.pk
        assert annotation.kind == "set_start"
        assert annotation.offset_ms == 1500

    @pytest.mark.parametrize("status", ["created", "cancelled", "failed"])
    def test_blocked_on_created_cancelled_failed(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)

        assert (
            _error_code(
                services.create_annotation, profile.user, str(session.pk), _annotation_data()
            )
            == "annotation_blocked"
        )
        assert not SessionAnnotation.objects.filter(session=session).exists()

    def test_not_found(self):
        profile = AthleteProfileFactory()
        assert (
            _error_code(
                services.create_annotation,
                profile.user,
                "00000000-0000-4000-8000-000000000000",
                _annotation_data(),
            )
            == "not_found"
        )

    def test_user_without_write_grant_refused(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=Session.Status.RECORDING)
        stranger = UserFactory()

        assert (
            _error_code(services.create_annotation, stranger, str(session.pk), _annotation_data())
            == "forbidden"
        )


class TestUpdateAnnotation:
    def test_updates_fields(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=Session.Status.RECORDING)
        annotation = services.create_annotation(profile.user, str(session.pk), _annotation_data())

        updated = services.update_annotation(
            profile.user, str(annotation.pk), {"offset_ms": 2000, "text": "fausse impulsion"}
        )

        assert updated.offset_ms == 2000
        assert updated.text == "fausse impulsion"
        # ``session`` et ``author`` ne sont jamais modifiables par l'API.
        assert updated.session_id == session.pk
        assert updated.author_id == profile.user.pk

    @pytest.mark.parametrize("status", ["created", "cancelled", "failed"])
    def test_blocked_on_created_cancelled_failed(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)
        annotation = SessionAnnotation.objects.create(
            session=session, author=profile.user, kind="note", offset_ms=0
        )

        assert _error_code(
            services.update_annotation, profile.user, str(annotation.pk), {"text": "x"}
        ) == ("annotation_blocked")

    def test_not_found(self):
        profile = AthleteProfileFactory()
        assert (
            _error_code(
                services.update_annotation,
                profile.user,
                "00000000-0000-4000-8000-000000000000",
                {"text": "x"},
            )
            == "not_found"
        )


class TestDeleteAnnotation:
    @pytest.mark.parametrize("status", ["recording", "completed"])
    def test_deletes(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)
        annotation = services.create_annotation(profile.user, str(session.pk), _annotation_data())

        services.delete_annotation(profile.user, str(annotation.pk))

        assert not SessionAnnotation.objects.filter(pk=annotation.pk).exists()

    @pytest.mark.parametrize("status", ["created", "cancelled", "failed"])
    def test_blocked_on_created_cancelled_failed(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)
        annotation = SessionAnnotation.objects.create(
            session=session, author=profile.user, kind="note", offset_ms=0
        )

        assert (
            _error_code(services.delete_annotation, profile.user, str(annotation.pk))
            == "annotation_blocked"
        )
        assert SessionAnnotation.objects.filter(pk=annotation.pk).exists()

    def test_user_without_write_grant_refused(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=Session.Status.RECORDING)
        annotation = services.create_annotation(profile.user, str(session.pk), _annotation_data())
        stranger = UserFactory()

        assert _error_code(services.delete_annotation, stranger, str(annotation.pk)) == "forbidden"


class TestUpdateSession:
    def test_updates_notes_and_acquisition_config(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)

        result = services.update_session(profile.user, str(session.pk), {"notes": "reprise"})

        assert result.notes == "reprise"

    @pytest.mark.parametrize("status", ["recording", "completed", "cancelled", "failed"])
    def test_locked_outside_created(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)

        assert (
            _error_code(services.update_session, profile.user, str(session.pk), {"notes": "x"})
            == "locked"
        )

    def test_user_without_write_grant_refused(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        stranger = UserFactory()

        assert (
            _error_code(services.update_session, stranger, str(session.pk), {"notes": "x"})
            == "forbidden"
        )

    def test_coach_with_write_grant_can_update(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        coach_user = UserFactory()
        from apps.coaches.tests.factories import CoachProfileFactory

        AccessGrantFactory(
            athlete=profile,
            grantee_coach=CoachProfileFactory(user=coach_user),
            scopes=[SCOPE_WRITE],
        )

        result = services.update_session(coach_user, str(session.pk), {"notes": "par le coach"})
        assert result.notes == "par le coach"
