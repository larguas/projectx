"""Tests de ``GET /api/v1/athletes/{id}/sessions/suggested-setup/``.

Setup de la DERNIÈRE séance du sportif (ordre ``-created_at``) — ou
``{"setup": null}`` s'il n'a pas encore de séance, ou si sa dernière séance a
été créée sans setup. 404 si le profil est inconnu ou non couvert par un grant
``sessions:read`` ; lecture non-propriétaire tracée (``session.viewed``).
"""

from datetime import timedelta
from uuid import uuid4

from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.sessions.tests.factories import make_session
from apps.setups.tests.factories import SensorSetupFactory
from apps.teams.tests.factories import AccessGrantFactory

URL = "/api/v1/athletes/{pk}/sessions/suggested-setup/"


def _url(profile):
    return URL.format(pk=profile.pk)


def _coach_with_grant(athlete, scopes):
    coach_user = UserFactory()
    coach = CoachProfileFactory(user=coach_user)
    AccessGrantFactory(athlete=athlete, grantee_coach=coach, scopes=scopes)
    return coach_user


class TestSuggestedSetup:
    def test_no_session_returns_null(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        response = client.get(_url(profile), **auth_headers(owner))
        assert response.status_code == 200
        assert response.json() == {"setup": None}

    def test_last_session_setup_returned(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        old_setup = SensorSetupFactory(athlete=profile)
        new_setup = SensorSetupFactory(athlete=profile)
        now = timezone.now()
        make_session(athlete=profile, setup=old_setup, created_at=now - timedelta(days=2))
        make_session(athlete=profile, setup=new_setup, created_at=now - timedelta(days=1))
        response = client.get(_url(profile), **auth_headers(owner))
        assert response.status_code == 200
        assert response.json()["setup"]["id"] == str(new_setup.pk)

    def test_last_session_without_setup_returns_null(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup = SensorSetupFactory(athlete=profile)
        now = timezone.now()
        make_session(athlete=profile, setup=setup, created_at=now - timedelta(days=2))
        make_session(athlete=profile, created_at=now - timedelta(days=1))  # sans setup
        response = client.get(_url(profile), **auth_headers(owner))
        assert response.status_code == 200
        assert response.json() == {"setup": None}

    def test_owner_read_not_audited(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup = SensorSetupFactory(athlete=profile)
        make_session(athlete=profile, setup=setup)
        client.get(_url(profile), **auth_headers(owner))
        assert not AuditEvent.objects.filter(action="session.viewed").exists()

    def test_coach_with_read_grant_sees_and_is_audited(self, client):
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        session = make_session(athlete=profile, setup=setup)
        coach_user = _coach_with_grant(profile, ["sessions:read"])
        response = client.get(_url(profile), **auth_headers(coach_user))
        assert response.status_code == 200
        assert response.json()["setup"]["id"] == str(setup.pk)
        event = AuditEvent.objects.get(action="session.viewed")
        assert event.actor_id == coach_user.pk
        assert event.target_id == session.pk

    def test_coach_without_grant_404(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        assert client.get(_url(profile), **auth_headers(coach_user)).status_code == 404

    def test_unknown_profile_404(self, client):
        owner = UserFactory()
        response = client.get(URL.format(pk=uuid4()), **auth_headers(owner))
        assert response.status_code == 404

    def test_anonymous_refused(self, client):
        profile = AthleteProfileFactory()
        assert client.get(_url(profile)).status_code == 401
