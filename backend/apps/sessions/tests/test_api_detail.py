"""Tests de ``GET/PATCH /api/v1/sessions/{id}/`` : détail et mise à jour.

Matrice de droits sur le détail : anonyme (401), propriétaire (sans traçage),
coach avec grant ``sessions:read`` (traçé — ``session.viewed``), sans grant
(404 — l'existence n'est pas révélée), membre d'équipe bénéficiaire,
superutilisateur. PATCH limité à ``notes`` / ``acquisition_config`` pendant
``created`` (``locked``, 409 sinon) ; le statut ne passe JAMAIS par un
sérialiseur (un champ ``status`` en entrée est ignoré).
"""

import json

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.sessions.tests.factories import make_session
from apps.teams.tests.factories import (
    AccessGrantFactory,
    TeamAccessGrantFactory,
    TeamFactory,
    TeamMembershipFactory,
)


def _url(session):
    return f"/api/v1/sessions/{session.pk}/"


def _patch(client, user, session, payload):
    return client.patch(
        _url(session),
        data=json.dumps(payload),
        content_type="application/json",
        **auth_headers(user),
    )


class TestSessionDetailPermissions:
    def test_anonymous_refused(self, client):
        session = make_session()
        assert client.get(_url(session)).status_code == 401

    def test_owner_sees_without_audit(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile)
        response = client.get(_url(session), **auth_headers(owner))
        assert response.status_code == 200
        assert response.json()["id"] == str(session.pk)
        assert not AuditEvent.objects.filter(action="session.viewed").exists()

    def test_coach_with_read_grant_sees_and_is_audited(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=["sessions:read"])
        response = client.get(_url(session), **auth_headers(coach_user))
        assert response.status_code == 200
        event = AuditEvent.objects.get(action="session.viewed")
        assert event.actor_id == coach_user.pk
        assert event.target_id == session.pk

    def test_coach_without_grant_gets_404(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        session = make_session()
        assert client.get(_url(session), **auth_headers(coach_user)).status_code == 404

    def test_team_member_with_team_grant_sees(self, client):
        team = TeamFactory()
        member_user = UserFactory()
        TeamMembershipFactory(team=team, user=member_user)
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        TeamAccessGrantFactory(athlete=profile, grantee_team=team, scopes=["sessions:read"])
        assert client.get(_url(session), **auth_headers(member_user)).status_code == 200

    def test_superuser_sees(self, client):
        superuser = UserFactory(is_superuser=True)
        session = make_session()
        assert client.get(_url(session), **auth_headers(superuser)).status_code == 200


class TestSessionDetailShape:
    def test_detail_has_channels_devices_annotations_editable(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        device = __import__(
            "apps.devices.tests.factories", fromlist=["DeviceFactory"]
        ).DeviceFactory(owner=owner)
        session = make_session(athlete=profile, channels=[(device, 1)])
        body = client.get(_url(session), **auth_headers(owner)).json()
        assert [c["channel_id"] for c in body["channels"]] == [1]
        assert [d["role"] for d in body["devices"]] == ["primary"]
        assert body["annotations"] == []
        assert body["editable"] is True  # propriétaire pendant ``created``


class TestSessionDetailPatch:
    def test_owner_patches_notes_during_created(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile)
        response = _patch(client, owner, session, {"notes": "réglage final"})
        assert response.status_code == 200
        assert response.json()["notes"] == "réglage final"
        session.refresh_from_db()
        assert session.notes == "réglage final"

    def test_owner_patches_acquisition_config_during_created(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile)
        response = _patch(client, owner, session, {"acquisition_config": {"sample_rate": 500}})
        assert response.status_code == 200
        assert response.json()["acquisition_config"] == {"sample_rate": 500}

    def test_patch_locked_outside_created(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile, status="recording")
        response = _patch(client, owner, session, {"notes": "trop tard"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "locked"

    def test_status_never_changed_via_patch(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        session = make_session(athlete=profile)
        response = _patch(client, owner, session, {"status": "recording"})
        assert response.status_code == 200
        session.refresh_from_db()
        assert session.status == "created"  # le champ est ignoré, pas appliqué

    def test_coach_with_read_only_grant_cannot_patch(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        session = make_session(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=["sessions:read"])
        response = _patch(client, coach_user, session, {"notes": "non"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_patch_unknown_session_404(self, client):
        owner = UserFactory()
        unknown = make_session()  # d'un autre sportif : invisible pour ``owner``
        response = _patch(client, owner, unknown, {"notes": "?"})
        assert response.status_code == 404
