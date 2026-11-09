"""Tests de ``GET /api/v1/sessions/`` : liste des séances visibles + filtres.

Matrice de droits : anonyme (401), propriétaire (sans traçage de ses propres
lectures), coach avec grant ``sessions:read`` (liste tracée —
``session.listed``), sans grant (liste vide), membre actif d'équipe bénéficiaire
d'un grant d'équipe, superutilisateur. Filtres : sportif, statut, dates,
exercice, appareil, type de séance, placement déclaré.
"""

from datetime import timedelta

from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.devices.tests.factories import DeviceFactory
from apps.exercises.tests.factories import ExerciseFactory
from apps.sessions.models import Session
from apps.sessions.tests.factories import make_session
from apps.teams.tests.factories import (
    AccessGrantFactory,
    TeamAccessGrantFactory,
    TeamFactory,
    TeamMembershipFactory,
)

LIST_URL = "/api/v1/sessions/"


class TestSessionListPermissions:
    def test_anonymous_refused(self, client):
        make_session()
        assert client.get(LIST_URL).status_code == 401

    def test_owner_sees_own_sessions_without_audit(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        mine = make_session(athlete=profile)
        make_session()  # d'un autre sportif : invisible pour ``owner``
        response = client.get(LIST_URL, **auth_headers(owner))
        assert response.status_code == 200
        ids = [s["id"] for s in response.json()["results"]]
        assert ids == [str(mine.pk)]
        assert not AuditEvent.objects.filter(action="session.listed").exists()

    def test_coach_with_read_grant_sees_and_list_is_audited(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=["sessions:read"])
        response = client.get(LIST_URL, **auth_headers(coach_user))
        assert response.status_code == 200
        assert [s["id"] for s in response.json()["results"]] == [str(session.pk)]
        event = AuditEvent.objects.get(action="session.listed")
        assert event.actor_id == coach_user.pk
        assert event.target_id is None
        assert event.metadata == {"granted_sessions": 1}

    def test_coach_without_grant_sees_nothing(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        make_session()
        response = client.get(LIST_URL, **auth_headers(coach_user))
        assert response.status_code == 200
        assert response.json()["results"] == []

    def test_team_member_sees_with_team_grant(self, client):
        team = TeamFactory()
        member_user = UserFactory()
        TeamMembershipFactory(team=team, user=member_user)
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        TeamAccessGrantFactory(athlete=profile, grantee_team=team, scopes=["sessions:read"])
        response = client.get(LIST_URL, **auth_headers(member_user))
        assert [s["id"] for s in response.json()["results"]] == [str(session.pk)]

    def test_superuser_sees_everything(self, client):
        superuser = UserFactory(is_superuser=True)
        sessions = [make_session(), make_session()]
        response = client.get(LIST_URL, **auth_headers(superuser))
        assert {s["id"] for s in response.json()["results"]} == {str(s.pk) for s in sessions}


class TestSessionListShape:
    def test_list_item_has_compact_references_and_warnings(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        make_session(athlete=profile)
        response = client.get(LIST_URL, **auth_headers(owner))
        body = response.json()["results"][0]
        assert body["warnings"] == ["setup_not_declared"]  # séance sans setup
        assert body["status"] == "created"
        assert body["athlete"]["id"] == str(profile.pk)
        assert "channels" not in body  # la liste ne porte pas les canaux
        assert "annotations" not in body
        assert "created_by" not in body  # identité du créateur jamais exposée


class TestSessionListFilters:
    """Filtres testés avec un superutilisateur (toutes les séances visibles)."""

    def _dataset(self):
        """Deux sportifs, quatre séances couvrant tous les filtres."""
        profile_a = AthleteProfileFactory()
        profile_b = AthleteProfileFactory()
        exercise = ExerciseFactory()
        device_a = DeviceFactory()
        device_b = DeviceFactory()

        s1 = make_session(athlete=profile_a)  # created, sans canal, sans setup
        s2 = make_session(
            athlete=profile_a, status="recording", exercise=exercise, channels=[(device_a, 1)]
        )
        s3 = make_session(
            athlete=profile_b,
            session_type="calibration",
            setup_declared=True,
            channels=[(device_b, 1)],
        )
        s4 = make_session(athlete=profile_b)
        # ``created_at`` est ``auto_now_add`` : un ``update()`` queryset passe
        # outre (utile pour les bornes de dates).
        Session.objects.filter(pk=s4.pk).update(created_at=timezone.now() - timedelta(days=10))
        return profile_a, profile_b, exercise, device_a, device_b, s1, s2, s3, s4

    def _ids(self, client, user, params):
        """Les paramètres de filtre passent par ``data`` (query string)."""
        response = client.get(LIST_URL, data=params, **auth_headers(user))
        assert response.status_code == 200
        return {s["id"] for s in response.json()["results"]}

    def test_filter_by_athlete(self, client):
        superuser = UserFactory(is_superuser=True)
        profile_a, _pb, _ex, _da, _db, s1, s2, _s3, _s4 = self._dataset()
        assert self._ids(client, superuser, {"athlete": str(profile_a.pk)}) == {
            str(s1.pk),
            str(s2.pk),
        }

    def test_filter_by_status(self, client):
        superuser = UserFactory(is_superuser=True)
        _pa, _pb, _ex, _da, _db, _s1, s2, _s3, _s4 = self._dataset()
        assert self._ids(client, superuser, {"status": "recording"}) == {str(s2.pk)}

    def test_filter_by_session_type(self, client):
        superuser = UserFactory(is_superuser=True)
        _pa, _pb, _ex, _da, _db, _s1, _s2, s3, _s4 = self._dataset()
        assert self._ids(client, superuser, {"session_type": "calibration"}) == {str(s3.pk)}

    def test_filter_by_exercise(self, client):
        superuser = UserFactory(is_superuser=True)
        _pa, _pb, exercise, _da, _db, _s1, s2, _s3, _s4 = self._dataset()
        assert self._ids(client, superuser, {"exercise": str(exercise.pk)}) == {str(s2.pk)}

    def test_filter_by_device(self, client):
        superuser = UserFactory(is_superuser=True)
        _pa, _pb, _ex, _da, device_b, _s1, _s2, s3, _s4 = self._dataset()
        assert self._ids(client, superuser, {"device": str(device_b.pk)}) == {str(s3.pk)}

    def test_filter_by_setup_declared(self, client):
        superuser = UserFactory(is_superuser=True)
        _pa, _pb, _ex, _da, _db, s1, s2, s3, s4 = self._dataset()
        assert self._ids(client, superuser, {"setup_declared": "true"}) == {str(s3.pk)}
        assert self._ids(client, superuser, {"setup_declared": "false"}) == {
            str(s1.pk),
            str(s2.pk),
            str(s4.pk),
        }

    def test_filter_by_created_at_bounds(self, client):
        superuser = UserFactory(is_superuser=True)
        _pa, _pb, _ex, _da, _db, s1, s2, s3, s4 = self._dataset()
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        assert self._ids(client, superuser, {"created_at_from": str(today)}) == {
            str(s1.pk),
            str(s2.pk),
            str(s3.pk),
        }
        assert self._ids(client, superuser, {"created_at_to": str(yesterday)}) == {str(s4.pk)}

    def test_invalid_status_value_refused(self, client):
        superuser = UserFactory(is_superuser=True)
        self._dataset()
        response = client.get(LIST_URL, data={"status": "bogus"}, **auth_headers(superuser))
        assert response.status_code == 400
