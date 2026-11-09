"""Tests des transitions de la machine à états (services).

Chaque transition passe par un service dédié sous ``select_for_update`` :
- validité / refus selon la machine à états du modèle (``invalid_transition``,
  409) ; horodatages ``started_at`` / ``ended_at`` posés par le service ;
- contrôle d'accès refait APRÈS le verrou (filet de sécurité — ``forbidden``) ;
- concurrence : deux transitions simultanées sur la même séance sont sérialisées,
  seule la première passe (test transactionnel avec deux threads) ;
- hook ``on_session_completed`` : appelé après ``complete_session``, un échec du
  hook ne casse jamais l'état de la séance (loggé, non propagé).
"""

import threading

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.sessions import services
from apps.sessions.models import Session
from apps.sessions.tests.factories import make_session
from apps.teams.tests.factories import AccessGrantFactory

from .helpers import SCOPE_WRITE


def _error_code(fn, *args):
    with pytest.raises(services.SessionsServiceError) as excinfo:
        fn(*args)
    return excinfo.value.code


class TestStartSession:
    def test_created_to_recording_sets_started_at(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        assert session.started_at is None

        result = services.start_session(profile.user, str(session.pk))

        assert result.status == Session.Status.RECORDING
        assert result.started_at is not None

    def test_refused_from_recording(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=Session.Status.RECORDING)
        assert (
            _error_code(services.start_session, profile.user, str(session.pk))
            == "invalid_transition"
        )

    @pytest.mark.parametrize("status", ["completed", "cancelled", "failed"])
    def test_refused_from_terminal_states(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)
        assert (
            _error_code(services.start_session, profile.user, str(session.pk))
            == "invalid_transition"
        )

    def test_not_found(self):
        profile = AthleteProfileFactory()
        assert (
            _error_code(
                services.start_session, profile.user, "00000000-0000-4000-8000-000000000000"
            )
            == "not_found"
        )


class TestCompleteSession:
    def test_recording_to_completed_sets_ended_at(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=Session.Status.RECORDING)
        assert session.ended_at is None

        result = services.complete_session(profile.user, str(session.pk))

        assert result.status == Session.Status.COMPLETED
        assert result.ended_at is not None

    def test_refused_from_created(self):
        """``created → completed`` n'existe pas : il faut enregistrer d'abord."""
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        assert (
            _error_code(services.complete_session, profile.user, str(session.pk))
            == "invalid_transition"
        )

    @pytest.mark.parametrize("status", ["cancelled", "failed"])
    def test_refused_from_other_terminal_states(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)
        assert (
            _error_code(services.complete_session, profile.user, str(session.pk))
            == "invalid_transition"
        )


class TestCancelSession:
    @pytest.mark.parametrize("status", ["created", "recording"])
    def test_cancelled_from_created_or_recording(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)

        result = services.cancel_session(profile.user, str(session.pk))

        assert result.status == Session.Status.CANCELLED
        assert result.ended_at is not None

    @pytest.mark.parametrize("status", ["completed", "cancelled", "failed"])
    def test_refused_from_terminal_states(self, status):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=status)
        assert (
            _error_code(services.cancel_session, profile.user, str(session.pk))
            == "invalid_transition"
        )


class TestFailSession:
    def test_recording_to_failed(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=Session.Status.RECORDING)

        result = services.fail_session(profile.user, str(session.pk))

        assert result.status == Session.Status.FAILED
        assert result.ended_at is not None

    def test_refused_from_created(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        assert (
            _error_code(services.fail_session, profile.user, str(session.pk))
            == "invalid_transition"
        )


class TestTransitionAccess:
    def test_user_without_write_grant_refused_after_lock(self):
        """Le contrôle d'écriture est refait APRÈS le verrou (filet de sécurité)."""
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        stranger = UserFactory()

        assert _error_code(services.start_session, stranger, str(session.pk)) == "forbidden"

    def test_coach_with_write_grant_can_transition(self):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        coach_user = UserFactory()
        from apps.coaches.tests.factories import CoachProfileFactory

        AccessGrantFactory(
            athlete=profile,
            grantee_coach=CoachProfileFactory(user=coach_user),
            scopes=[SCOPE_WRITE],
        )

        result = services.start_session(coach_user, str(session.pk))
        assert result.status == Session.Status.RECORDING


class TestCompletedHook:
    def test_hook_called_with_completed_session(self, monkeypatch):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=Session.Status.RECORDING)
        calls = []
        monkeypatch.setattr(services, "on_session_completed", lambda s: calls.append(s.pk))

        result = services.complete_session(profile.user, str(session.pk))

        assert result.status == Session.Status.COMPLETED
        assert calls == [session.pk]

    def test_hook_failure_does_not_break_state(self, monkeypatch):
        """Un hook qui lève ne casse PAS la transition (loggé, jamais propagé)."""

        def broken_hook(session):
            raise RuntimeError("explosion du hook")

        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=Session.Status.RECORDING)
        monkeypatch.setattr(services, "on_session_completed", broken_hook)

        result = services.complete_session(profile.user, str(session.pk))

        assert result.status == Session.Status.COMPLETED
        session.refresh_from_db()
        assert session.status == Session.Status.COMPLETED


class TestTransitionConcurrency:
    # ``transaction=True`` : les deux threads doivent voir des verrous réels, hors
    # de la transaction de rollback de pytest-django. Le flush post-test effacerait
    # sinon les données seedées (migrations de données) dans la base réutilisée
    # (``--reuse-db``) : ``serialized_rollback=True`` fait restaurer l'état de la
    # base tel qu'au début de session après chaque test (mécanisme Django).
    @pytest.mark.django_db(transaction=True, serialized_rollback=True)
    def test_concurrent_complete_and_cancel_only_one_wins(self):
        """Deux transitions simultanées : sérialisées par ``select_for_update``,
        seule la première passe, la seconde reçoit ``invalid_transition``."""
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile, status=Session.Status.RECORDING)
        barrier = threading.Barrier(2)
        results: dict[str, str] = {}

        def run(name, func):
            barrier.wait()  # départ synchronisé des deux threads
            try:
                func(profile.user, str(session.pk))
                results[name] = "ok"
            except services.SessionsServiceError as exc:
                results[name] = exc.code

        threads = [
            threading.Thread(target=run, args=("complete", services.complete_session)),
            threading.Thread(target=run, args=("cancel", services.cancel_session)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert set(results.values()) == {"ok", "invalid_transition"}
        session.refresh_from_db()
        assert session.status in (Session.Status.COMPLETED, Session.Status.CANCELLED)
