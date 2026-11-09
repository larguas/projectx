"""Tests des transitions ``POST /api/v1/sessions/{id}/start|complete|cancel/``.

Machine à états modifiable UNIQUEMENT par ces endpoints (jamais un sérialiseur) :
``created → recording → completed``, ``created | recording → cancelled`` ; toute
autre transition renvoie 409 ``invalid_transition``. Écriture = scope
``sessions:write`` sur le sportif (403 sinon ; 404 si la séance n'est pas lisible).
Chaque transition réussie est tracée pour TOUS les acteurs (``session.started`` /
``session.completed`` / ``session.cancelled``) — mutations sensibles.
"""

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.sessions.tests.factories import make_session
from apps.teams.tests.factories import AccessGrantFactory


def _coach_with_grant(athlete, scopes):
    coach_user = UserFactory()
    coach = CoachProfileFactory(user=coach_user)
    AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=scopes)
    return coach_user


class TestStartTransition:
    def test_start_from_created(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile)
        response = client.post(f"/api/v1/sessions/{session.pk}/start/", **auth_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "recording"
        assert body["started_at"] is not None
        session.refresh_from_db()
        assert session.status == "recording"

    def test_start_is_audited_for_owner_too(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile)
        client.post(f"/api/v1/sessions/{session.pk}/start/", **auth_headers(owner))
        event = AuditEvent.objects.get(action="session.started")
        assert event.actor_id == owner.pk

    def test_start_twice_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="recording")
        response = client.post(f"/api/v1/sessions/{session.pk}/start/", **auth_headers(owner))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_start_from_completed_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="completed")
        response = client.post(f"/api/v1/sessions/{session.pk}/start/", **auth_headers(owner))
        assert response.status_code == 409

    def test_anonymous_refused(self, client):
        session = make_session()
        assert client.post(f"/api/v1/sessions/{session.pk}/start/").status_code == 401

    def test_coach_read_only_grant_refused(self, client):
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        coach_user = _coach_with_grant(profile, ["sessions:read"])
        response = client.post(f"/api/v1/sessions/{session.pk}/start/", **auth_headers(coach_user))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_unknown_session_404(self, client):
        owner = UserFactory()
        foreign = make_session()  # d'un autre sportif : invisible
        response = client.post(f"/api/v1/sessions/{foreign.pk}/start/", **auth_headers(owner))
        assert response.status_code == 404


class TestCompleteTransition:
    def test_complete_from_recording(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="recording")
        response = client.post(f"/api/v1/sessions/{session.pk}/complete/", **auth_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["ended_at"] is not None
        assert AuditEvent.objects.filter(action="session.completed").exists()

    def test_complete_from_created_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile)
        response = client.post(f"/api/v1/sessions/{session.pk}/complete/", **auth_headers(owner))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_complete_from_cancelled_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="cancelled")
        response = client.post(f"/api/v1/sessions/{session.pk}/complete/", **auth_headers(owner))
        assert response.status_code == 409


class TestCancelTransition:
    def test_cancel_from_created(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile)
        response = client.post(f"/api/v1/sessions/{session.pk}/cancel/", **auth_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "cancelled"
        assert body["ended_at"] is not None
        assert AuditEvent.objects.filter(action="session.cancelled").exists()

    def test_cancel_from_recording(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="recording")
        response = client.post(f"/api/v1/sessions/{session.pk}/cancel/", **auth_headers(owner))
        assert response.status_code == 200

    def test_cancel_from_completed_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="completed")
        response = client.post(f"/api/v1/sessions/{session.pk}/cancel/", **auth_headers(owner))
        assert response.status_code == 409

    def test_cancel_from_failed_refused(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="failed")
        response = client.post(f"/api/v1/sessions/{session.pk}/cancel/", **auth_headers(owner))
        assert response.status_code == 409
