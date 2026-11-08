"""Tests des permissions et contrats d'endpoints de la feature 05b (app ``setups``).

Matrice de droits sur les 9 endpoints : anonyme (401), propriétaire du profil
sportif (accès total, sans traçage de ses propres lectures), coach avec grant
``setups:read`` / ``setups:write`` / sans grant (404 — l'existence n'est pas
révélée), membre actif d'équipe bénéficiaire d'un grant d'équipe,
superutilisateur. Sont aussi vérifiés les contrats métier : refus 409 des
mutations sur setup utilisé (``setup_frozen``), ``name_taken``,
``already_invalidated`` ; le niveau ``unknown`` de la comparaison quand un
setup n'est pas lisible par le demandeur ; les filtres de calibrations
(``setup``, ``type``, ``applicable``) ; et le traçage d'audit —
``setup.viewed``, ``setup.listed``, ``calibration.listed`` pour les lectures
non propriétaire, ``calibration.invalidated`` pour TOUS les acteurs.
"""

import json
import uuid

from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.exercises.tests.factories import MuscleFactory
from apps.setups.models import PlacementGuide, SensorSetup
from apps.setups.services import new_version as new_version_service
from apps.setups.tests.factories import (
    CalibrationFactory,
    SensorSetupFactory,
    SetupChannelFactory,
    mark_used,
)
from apps.teams.tests.factories import (
    AccessGrantFactory,
    TeamAccessGrantFactory,
    TeamFactory,
    TeamMembershipFactory,
)

SCOPE_READ = "setups:read"
SCOPE_WRITE = "setups:write"


def _patch(client, user, setup_id, payload):
    url = f"/api/v1/setups/{setup_id}/"
    return client.patch(
        url, data=json.dumps(payload), content_type="application/json", **auth_headers(user)
    )


def _put_json(client, user, url, payload):
    return client.put(
        url, data=json.dumps(payload), content_type="application/json", **auth_headers(user)
    )


class TestSetupList:
    """``GET /api/v1/setups/`` : liste des setups visibles."""

    def test_anonymous_refused(self, client):
        assert client.get("/api/v1/setups/").status_code == 401

    def test_owner_sees_own_setups_without_audit(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup = SensorSetupFactory(athlete=profile)
        other = SensorSetupFactory()  # d'un autre sportif : invisible pour ``owner``
        response = client.get("/api/v1/setups/", **auth_headers(owner))
        assert response.status_code == 200
        ids = [s["id"] for s in response.json()["results"]]
        assert ids == [str(setup.pk)]
        assert str(other.pk) not in ids
        assert not AuditEvent.objects.filter(action="setup.listed").exists()

    def test_coach_with_read_grant_sees_and_list_is_audited(self, client):
        """``setups:read`` ouvre la liste ; la lecture est tracée (``setup.listed``)."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.get("/api/v1/setups/", **auth_headers(coach_user))
        assert response.status_code == 200
        assert [s["id"] for s in response.json()["results"]] == [str(setup.pk)]
        event = AuditEvent.objects.get(action="setup.listed")
        assert event.actor_id == coach_user.pk
        assert event.target_id is None
        assert event.metadata == {"granted_setups": 1}

    def test_coach_without_grant_sees_nothing(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        SensorSetupFactory()
        response = client.get("/api/v1/setups/", **auth_headers(coach_user))
        assert response.status_code == 200
        assert response.json()["results"] == []

    def test_team_member_sees_with_team_grant(self, client):
        """Un membre ACTIF de l'équipe bénéficiaire d'un grant y accède."""
        team = TeamFactory()
        member_user = UserFactory()
        TeamMembershipFactory(team=team, user=member_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        TeamAccessGrantFactory(athlete=profile, grantee_team=team, scopes=[SCOPE_READ])
        response = client.get("/api/v1/setups/", **auth_headers(member_user))
        assert [s["id"] for s in response.json()["results"]] == [str(setup.pk)]

    def test_superuser_sees_everything(self, client):
        superuser = UserFactory(is_superuser=True)
        setups = [SensorSetupFactory(), SensorSetupFactory()]
        response = client.get("/api/v1/setups/", **auth_headers(superuser))
        assert {s["id"] for s in response.json()["results"]} == {str(s.pk) for s in setups}


class TestSetupCreate:
    """``POST /api/v1/setups/`` : création pour un sportif rattaché."""

    def test_anonymous_cannot_create(self, client):
        assert post_json(client, "/api/v1/setups/", {"name": "Nope"}).status_code == 401

    def test_owner_creates_for_own_athlete(self, client):
        user = UserFactory()
        profile = AthleteProfileFactory(user=user)
        response = post_json(
            client,
            "/api/v1/setups/",
            {"name": "Placement biceps", "athlete": str(profile.pk)},
            **auth_headers(user),
        )
        assert response.status_code == 201, response.data
        body = response.json()
        assert body["athlete"]["id"] == str(profile.pk)
        assert body["version"] == 1
        assert body["detail_level"] == "simple"
        assert body["editable"] is True
        assert "created_by" not in body  # donnée d'audit, jamais exposée

    def test_coach_creates_with_write_grant(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_WRITE])
        response = post_json(
            client,
            "/api/v1/setups/",
            {"name": "Placement coach", "athlete": str(profile.pk)},
            **auth_headers(coach_user),
        )
        assert response.status_code == 201, response.data

    def test_read_only_grant_cannot_create(self, client):
        """``setups:read`` n'ouvre pas la création (écriture requise) : 403."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = post_json(
            client,
            "/api/v1/setups/",
            {"name": "Injection ?", "athlete": str(profile.pk)},
            **auth_headers(coach_user),
        )
        assert response.status_code == 403

    def test_no_grant_cannot_create(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        response = post_json(
            client,
            "/api/v1/setups/",
            {"name": "Injection ?", "athlete": str(profile.pk)},
            **auth_headers(coach_user),
        )
        assert response.status_code == 403

    def test_duplicate_name_409(self, client):
        """L'identité d'un setup est ``(athlete, name, version)`` : doublon refusé."""
        user = UserFactory()
        profile = AthleteProfileFactory(user=user)
        SensorSetupFactory(athlete=profile, name="Biceps")
        response = post_json(
            client,
            "/api/v1/setups/",
            {"name": "Biceps", "athlete": str(profile.pk)},
            **auth_headers(user),
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "name_taken"


class TestSetupDetailRead:
    """``GET /api/v1/setups/{id}/`` : détail visible selon ``can_read_setup``."""

    def test_anonymous_refused(self, client):
        setup = SensorSetupFactory()
        assert client.get(f"/api/v1/setups/{setup.pk}/").status_code == 401

    def test_owner_reads_without_audit_and_editable(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup = SensorSetupFactory(athlete=profile)
        response = client.get(f"/api/v1/setups/{setup.pk}/", **auth_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == setup.name
        assert body["editable"] is True
        assert not AuditEvent.objects.filter(action="setup.viewed").exists()

    def test_coach_reads_with_read_grant_and_viewed_audit(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.get(f"/api/v1/setups/{setup.pk}/", **auth_headers(coach_user))
        assert response.status_code == 200
        event = AuditEvent.objects.get(action="setup.viewed")
        assert event.actor_id == coach_user.pk
        assert event.athlete_id == profile.pk
        assert event.target_type == "SensorSetup"
        assert str(event.target_id) == str(setup.pk)

    def test_coach_without_grant_gets_404(self, client):
        """Sans grant : 404 — l'existence du setup n'est pas révélée."""
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        setup = SensorSetupFactory()
        response = client.get(f"/api/v1/setups/{setup.pk}/", **auth_headers(coach_user))
        assert response.status_code == 404

    def test_team_member_reads_with_team_grant(self, client):
        team = TeamFactory()
        member_user = UserFactory()
        TeamMembershipFactory(team=team, user=member_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        TeamAccessGrantFactory(athlete=profile, grantee_team=team, scopes=[SCOPE_READ])
        response = client.get(f"/api/v1/setups/{setup.pk}/", **auth_headers(member_user))
        assert response.status_code == 200

    def test_superuser_reads_any_setup(self, client):
        superuser = UserFactory(is_superuser=True)
        setup = SensorSetupFactory()
        response = client.get(f"/api/v1/setups/{setup.pk}/", **auth_headers(superuser))
        assert response.status_code == 200

    def test_unknown_id_404(self, client):
        user = UserFactory()
        response = client.get(f"/api/v1/setups/{uuid.uuid4()}/", **auth_headers(user))
        assert response.status_code == 404


class TestSetupDetailWrite:
    """``PATCH/DELETE /api/v1/setups/{id}/`` : écriture selon ``setups:write``."""

    def test_anonymous_cannot_patch(self, client):
        setup = SensorSetupFactory()
        response = client.patch(
            f"/api/v1/setups/{setup.pk}/",
            data=json.dumps({"name": "Nope"}),
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_owner_patches_name_and_notes(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup = SensorSetupFactory(athlete=profile)
        response = _patch(client, owner, setup.pk, {"name": "V2", "notes": "Repos allongé"})
        assert response.status_code == 200, response.data
        setup.refresh_from_db()
        assert setup.name == "V2"
        assert setup.notes == "Repos allongé"

    def test_read_only_grant_cannot_patch(self, client):
        """Un grant ``setups:read`` n'ouvre pas l'écriture : 403 (setup visible)."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = _patch(client, coach_user, setup.pk, {"name": "Hacking"})
        assert response.status_code == 403

    def test_write_grant_can_patch(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ, SCOPE_WRITE])
        response = _patch(client, coach_user, setup.pk, {"notes": "Semaine 3"})
        assert response.status_code == 200, response.data
        setup.refresh_from_db()
        assert setup.notes == "Semaine 3"

    def test_no_grant_gets_404_on_patch(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        setup = SensorSetupFactory()
        response = _patch(client, coach_user, setup.pk, {"name": "Intrusion"})
        assert response.status_code == 404

    def test_owner_deletes_unused_setup(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup = SensorSetupFactory(athlete=profile)
        SetupChannelFactory(setup=setup)
        response = client.delete(f"/api/v1/setups/{setup.pk}/", **auth_headers(owner))
        assert response.status_code == 204
        assert not SensorSetup.objects.filter(pk=setup.pk).exists()

    def test_read_only_grant_cannot_delete(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.delete(f"/api/v1/setups/{setup.pk}/", **auth_headers(coach_user))
        assert response.status_code == 403
        assert SensorSetup.objects.filter(pk=setup.pk).exists()

    def test_write_grant_can_delete(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ, SCOPE_WRITE])
        response = client.delete(f"/api/v1/setups/{setup.pk}/", **auth_headers(coach_user))
        assert response.status_code == 204
        assert not SensorSetup.objects.filter(pk=setup.pk).exists()

    def test_other_user_404_on_delete(self, client):
        other = UserFactory()
        setup = SensorSetupFactory()
        response = client.delete(f"/api/v1/setups/{setup.pk}/", **auth_headers(other))
        assert response.status_code == 404
        assert SensorSetup.objects.filter(pk=setup.pk).exists()

    def test_used_setup_patch_refused_409(self, client):
        """Setup utilisé (figé) : PATCH refusé en service — ``setup_frozen``."""
        owner = UserFactory()
        setup = mark_used(SensorSetupFactory(athlete=AthleteProfileFactory(user=owner)))
        response = _patch(client, owner, setup.pk, {"name": "Trop tard"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "setup_frozen"

    def test_used_setup_delete_refused_409(self, client):
        """Une séance ne doit jamais perdre son placement : DELETE refusé."""
        owner = UserFactory()
        setup = mark_used(SensorSetupFactory(athlete=AthleteProfileFactory(user=owner)))
        response = client.delete(f"/api/v1/setups/{setup.pk}/", **auth_headers(owner))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "setup_frozen"
        assert SensorSetup.objects.filter(pk=setup.pk).exists()


class TestSetupNewVersion:
    """``POST /api/v1/setups/{id}/new-version/`` : version n+1 (lignée parent)."""

    def test_anonymous_refused(self, client):
        setup = SensorSetupFactory()
        assert client.post(f"/api/v1/setups/{setup.pk}/new-version/").status_code == 401

    def test_owner_creates_version_of_used_setup(self, client):
        """Le seul moyen de modifier un setup utilisé : une nouvelle version."""
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        used = mark_used(SensorSetupFactory(athlete=profile))
        SetupChannelFactory(setup=used)
        response = post_json(
            client, f"/api/v1/setups/{used.pk}/new-version/", {}, **auth_headers(owner)
        )
        assert response.status_code == 201, response.data
        body = response.json()
        assert body["version"] == 2
        assert body["parent"] == str(used.pk)
        assert body["is_current"] is True
        assert len(body["channels"]) == 1
        used.refresh_from_db()
        assert used.is_current is False

    def test_read_only_grant_cannot_new_version(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = post_json(
            client, f"/api/v1/setups/{setup.pk}/new-version/", {}, **auth_headers(coach_user)
        )
        assert response.status_code == 403

    def test_no_grant_404_on_new_version(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        setup = SensorSetupFactory()
        response = post_json(
            client, f"/api/v1/setups/{setup.pk}/new-version/", {}, **auth_headers(coach_user)
        )
        assert response.status_code == 404


class TestSetupChannels:
    """``GET/PUT /api/v1/setups/{id}/channels/`` : lecture et remplacement atomique."""

    def test_anonymous_refused(self, client):
        setup = SensorSetupFactory()
        assert client.get(f"/api/v1/setups/{setup.pk}/channels/").status_code == 401

    def test_owner_reads_channels_without_audit(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup = SensorSetupFactory(athlete=profile)
        SetupChannelFactory(setup=setup)
        response = client.get(f"/api/v1/setups/{setup.pk}/channels/", **auth_headers(owner))
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert not AuditEvent.objects.filter(action="setup.viewed").exists()

    def test_coach_reads_channels_with_viewed_audit(self, client):
        """La lecture des canaux par un non-propriétaire est tracée comme le détail."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.get(f"/api/v1/setups/{setup.pk}/channels/", **auth_headers(coach_user))
        assert response.status_code == 200
        assert AuditEvent.objects.filter(action="setup.viewed").count() == 1

    def test_no_grant_404_on_channels(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        setup = SensorSetupFactory()
        response = client.get(f"/api/v1/setups/{setup.pk}/channels/", **auth_headers(coach_user))
        assert response.status_code == 404

    def test_owner_replaces_channels_json_and_detail_level_recomputed(self, client):
        """Remplacement ATOMIQUE en JSON ; le niveau de détail est recalculé."""
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup = SensorSetupFactory(athlete=profile)
        muscle = MuscleFactory()
        url = f"/api/v1/setups/{setup.pk}/channels/"
        response = _put_json(
            client,
            owner,
            url,
            {
                "channels": [
                    {
                        "channel_id": 1,
                        "muscle": str(muscle.pk),
                        "side": "left",
                        "position_note": "3 cm sous l'acromion",
                    }
                ]
            },
        )
        assert response.status_code == 200, response.data
        setup.refresh_from_db()
        assert setup.detail_level == SensorSetup.DetailLevel.DETAILED
        # Liste vide : retour au mode simple (champs détaillés vides).
        response = _put_json(client, owner, url, {"channels": []})
        assert response.status_code == 200
        setup.refresh_from_db()
        assert setup.detail_level == SensorSetup.DetailLevel.SIMPLE

    def test_read_only_grant_cannot_replace_channels(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        muscle = MuscleFactory()
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = _put_json(
            client,
            coach_user,
            f"/api/v1/setups/{setup.pk}/channels/",
            {"channels": [{"channel_id": 1, "muscle": str(muscle.pk)}]},
        )
        assert response.status_code == 403

    def test_used_setup_channels_replace_refused_409(self, client):
        owner = UserFactory()
        setup = mark_used(SensorSetupFactory(athlete=AthleteProfileFactory(user=owner)))
        muscle = MuscleFactory()
        response = _put_json(
            client,
            owner,
            f"/api/v1/setups/{setup.pk}/channels/",
            {"channels": [{"channel_id": 1, "muscle": str(muscle.pk)}]},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "setup_frozen"


class TestSetupCompare:
    """``GET /api/v1/setups/compare/?a={id}&b={id}`` : niveau de comparabilité."""

    def test_anonymous_refused(self, client):
        setup = SensorSetupFactory()
        url = f"/api/v1/setups/compare/?a={setup.pk}&b={setup.pk}"
        assert client.get(url).status_code == 401

    def test_missing_params_400(self, client):
        user = UserFactory()
        response = client.get("/api/v1/setups/compare/", **auth_headers(user))
        assert response.status_code == 400

    def test_owner_compares_own_setups(self, client):
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup = SensorSetupFactory(athlete=profile)
        url = f"/api/v1/setups/compare/?a={setup.pk}&b={setup.pk}"
        response = client.get(url, **auth_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["level"] == "identical"
        assert isinstance(body["reasons"], list) and body["reasons"]

    def test_non_readable_setup_is_unknown(self, client):
        """Un setup non lisible compte comme ABSENT : niveau ``unknown``.

        Le coach a un grant sur le sportif de ``a`` seulement ; ``b`` (d'un
        autre sportif) n'est pas révélé — même réponse que s'il n'existait pas.
        """
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile_a = AthleteProfileFactory()
        setup_a = SensorSetupFactory(athlete=profile_a)
        AccessGrantFactory(athlete=profile_a, grantee_coach=coach, scopes=[SCOPE_READ])
        setup_b = SensorSetupFactory()  # autre sportif, aucun grant
        url = f"/api/v1/setups/compare/?a={setup_a.pk}&b={setup_b.pk}"
        response = client.get(url, **auth_headers(coach_user))
        assert response.status_code == 200
        assert response.json()["level"] == "unknown"

    def test_unknown_uuid_is_unknown(self, client):
        user = UserFactory()
        setup = SensorSetupFactory(athlete=AthleteProfileFactory(user=user))
        url = f"/api/v1/setups/compare/?a={setup.pk}&b={uuid.uuid4()}"
        response = client.get(url, **auth_headers(user))
        assert response.status_code == 200
        assert response.json()["level"] == "unknown"


class TestAthleteCurrentSetups:
    """``GET /api/v1/athletes/{id}/setups/current/`` : versions courantes."""

    def test_anonymous_refused(self, client):
        profile = AthleteProfileFactory()
        assert client.get(f"/api/v1/athletes/{profile.pk}/setups/current/").status_code == 401

    def test_owner_sees_current_versions_without_audit(self, client):
        """Seules les versions ``is_current=True`` sont renvoyées."""
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        used = mark_used(SensorSetupFactory(athlete=profile))
        current = new_version_service(owner, used, {"placement_unchanged": False})
        response = client.get(
            f"/api/v1/athletes/{profile.pk}/setups/current/", **auth_headers(owner)
        )
        assert response.status_code == 200
        assert [s["id"] for s in response.json()["results"]] == [str(current.pk)]
        assert not AuditEvent.objects.filter(action="setup.listed").exists()

    def test_coach_with_read_grant_and_listed_audit(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        SensorSetupFactory(athlete=profile)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.get(
            f"/api/v1/athletes/{profile.pk}/setups/current/", **auth_headers(coach_user)
        )
        assert response.status_code == 200
        event = AuditEvent.objects.get(action="setup.listed")
        assert event.actor_id == coach_user.pk
        assert event.athlete_id == profile.pk
        assert event.metadata == {"granted_setups": 1}

    def test_coach_without_grant_404(self, client):
        """Profil non couvert par un grant ``setups:read`` : 404 (pas d'existence révélée)."""
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        response = client.get(
            f"/api/v1/athletes/{profile.pk}/setups/current/", **auth_headers(coach_user)
        )
        assert response.status_code == 404

    def test_team_member_sees_with_team_grant(self, client):
        team = TeamFactory()
        member_user = UserFactory()
        TeamMembershipFactory(team=team, user=member_user)
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        TeamAccessGrantFactory(athlete=profile, grantee_team=team, scopes=[SCOPE_READ])
        response = client.get(
            f"/api/v1/athletes/{profile.pk}/setups/current/", **auth_headers(member_user)
        )
        assert [s["id"] for s in response.json()["results"]] == [str(setup.pk)]


class TestAthleteCalibrations:
    """``GET /api/v1/athletes/{id}/calibrations/`` : calibrations + filtres."""

    @staticmethod
    def _dataset():
        """Sportif avec deux setups et cinq calibrations (tous les états)."""
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        setup_a = SensorSetupFactory(athlete=profile, name="A")
        setup_b = SensorSetupFactory(athlete=profile, name="B")
        mvc_a = CalibrationFactory(setup=setup_a, type="mvc")
        rest_a = CalibrationFactory(setup=setup_a, type="rest_baseline", values={})
        other_setup = CalibrationFactory(setup=setup_b)
        expired = CalibrationFactory(
            setup=setup_a, valid_until=timezone.now() - timezone.timedelta(days=1)
        )
        invalidated = CalibrationFactory(setup=setup_a)
        invalidated.invalidated_at = timezone.now()
        invalidated.invalidation_reason = "test"
        invalidated.save(update_fields=("invalidated_at", "invalidation_reason", "updated_at"))
        return owner, profile, setup_a, setup_b, mvc_a, rest_a, other_setup, expired, invalidated

    def test_anonymous_refused(self, client):
        profile = AthleteProfileFactory()
        assert client.get(f"/api/v1/athletes/{profile.pk}/calibrations/").status_code == 401

    def test_owner_lists_calibrations_without_audit(self, client):
        owner, profile, *_ = self._dataset()
        response = client.get(f"/api/v1/athletes/{profile.pk}/calibrations/", **auth_headers(owner))
        assert response.status_code == 200
        assert len(response.json()["results"]) == 5
        assert not AuditEvent.objects.filter(action="calibration.listed").exists()

    def test_coach_with_read_grant_and_listed_audit(self, client):
        _, profile, *_ = self._dataset()
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.get(
            f"/api/v1/athletes/{profile.pk}/calibrations/", **auth_headers(coach_user)
        )
        assert response.status_code == 200
        event = AuditEvent.objects.get(action="calibration.listed")
        assert event.actor_id == coach_user.pk
        assert event.athlete_id == profile.pk
        assert event.metadata == {"granted_calibrations": 5}

    def test_coach_without_grant_404(self, client):
        _, profile, *_ = self._dataset()
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        response = client.get(
            f"/api/v1/athletes/{profile.pk}/calibrations/", **auth_headers(coach_user)
        )
        assert response.status_code == 404

    def test_filter_by_type(self, client):
        owner, profile, *_rest = self._dataset()
        url = f"/api/v1/athletes/{profile.pk}/calibrations/?type=rest_baseline"
        response = client.get(url, **auth_headers(owner))
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["type"] == "rest_baseline"

    def test_filter_by_setup(self, client):
        owner, profile, setup_a, *_rest = self._dataset()
        url = f"/api/v1/athletes/{profile.pk}/calibrations/?setup={setup_a.pk}"
        response = client.get(url, **auth_headers(owner))
        assert response.status_code == 200
        results = response.json()["results"]
        # Quatre calibrations sur le setup A (mvc, repos, expirée, invalidée).
        assert len(results) == 4
        assert {r["setup"]["id"] for r in results} == {str(setup_a.pk)}

    def test_filter_applicable_true_excludes_invalidated_and_expired(self, client):
        owner, profile, *_rest = self._dataset()
        url = f"/api/v1/athletes/{profile.pk}/calibrations/?applicable=true"
        response = client.get(url, **auth_headers(owner))
        results = response.json()["results"]
        # MVC + baseline du setup A ; la calibration du setup B reste applicable.
        assert len(results) == 3
        assert all(r["applicable"] is True for r in results)

    def test_filter_applicable_false(self, client):
        owner, profile, *_rest = self._dataset()
        url = f"/api/v1/athletes/{profile.pk}/calibrations/?applicable=false"
        response = client.get(url, **auth_headers(owner))
        results = response.json()["results"]
        # Expirée + invalidée (la calibration du setup B est applicable).
        assert len(results) == 2
        assert all(r["applicable"] is False for r in results)

    def test_invalid_type_param_400(self, client):
        owner, profile, *_rest = self._dataset()
        url = f"/api/v1/athletes/{profile.pk}/calibrations/?type=quantum"
        response = client.get(url, **auth_headers(owner))
        assert response.status_code == 400


class TestCalibrationInvalidate:
    """``POST /api/v1/calibrations/{id}/invalidate/`` : invalidation irréversible."""

    def test_anonymous_refused(self, client):
        calibration = CalibrationFactory()
        assert client.post(f"/api/v1/calibrations/{calibration.pk}/invalidate/").status_code == 401

    def test_owner_invalidates_with_audit(self, client):
        """L'invalidation est tracée pour TOUS les acteurs, y compris le propriétaire."""
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        calibration = CalibrationFactory(setup=SensorSetupFactory(athlete=profile))
        response = post_json(
            client,
            f"/api/v1/calibrations/{calibration.pk}/invalidate/",
            {"reason": "MVC trop basse"},
            **auth_headers(owner),
        )
        assert response.status_code == 200, response.data
        body = response.json()
        assert body["invalidated_at"] is not None
        assert body["invalidation_reason"] == "MVC trop basse"
        assert body["applicable"] is False
        event = AuditEvent.objects.get(action="calibration.invalidated")
        assert event.actor_id == owner.pk
        assert event.athlete_id == profile.pk
        assert event.target_type == "Calibration"
        assert str(event.target_id) == str(calibration.pk)

    def test_read_only_grant_cannot_invalidate(self, client):
        """L'invalidation exige ``setups:write`` : un grant lecture seule est refusé."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        calibration = CalibrationFactory(setup=SensorSetupFactory(athlete=profile))
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = post_json(
            client,
            f"/api/v1/calibrations/{calibration.pk}/invalidate/",
            {},
            **auth_headers(coach_user),
        )
        assert response.status_code == 403

    def test_write_grant_can_invalidate_with_audit(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        calibration = CalibrationFactory(setup=SensorSetupFactory(athlete=profile))
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ, SCOPE_WRITE])
        response = post_json(
            client,
            f"/api/v1/calibrations/{calibration.pk}/invalidate/",
            {},
            **auth_headers(coach_user),
        )
        assert response.status_code == 200, response.data
        event = AuditEvent.objects.get(action="calibration.invalidated")
        assert event.actor_id == coach_user.pk

    def test_no_grant_404_on_invalidate(self, client):
        """Calibration non lisible (pas de grant) : 404 — existence non révélée."""
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        calibration = CalibrationFactory()
        response = post_json(
            client,
            f"/api/v1/calibrations/{calibration.pk}/invalidate/",
            {},
            **auth_headers(coach_user),
        )
        assert response.status_code == 404

    def test_already_invalidated_409(self, client):
        """L'invalidation est irréversible : une seconde tentative est refusée."""
        owner = UserFactory()
        profile = AthleteProfileFactory(user=owner)
        calibration = CalibrationFactory(setup=SensorSetupFactory(athlete=profile))
        url = f"/api/v1/calibrations/{calibration.pk}/invalidate/"
        response = post_json(client, url, {}, **auth_headers(owner))
        assert response.status_code == 200
        response = post_json(client, url, {"reason": "Encore ?"}, **auth_headers(owner))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "already_invalidated"


class TestPlacementGuide:
    """``GET /api/v1/muscles/{id}/placement-guide/`` : catalogue en lecture seule."""

    def test_anonymous_refused(self, client):
        muscle = MuscleFactory()
        assert client.get(f"/api/v1/muscles/{muscle.pk}/placement-guide/").status_code == 401

    def test_any_authenticated_user_reads_guide(self, client):
        """Catalogue sans profil rattaché : aucun grant requis (comme les muscles)."""
        user = UserFactory()
        muscle = MuscleFactory()
        guide = PlacementGuide.objects.create(
            muscle=muscle,
            title="Placement biceps",
            instructions="À mi-bras, côté latéral.",
            reference="Hermens et al., 2007 (SENIAM)",
        )
        response = client.get(f"/api/v1/muscles/{muscle.pk}/placement-guide/", **auth_headers(user))
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(guide.pk)
        assert body["muscle"]["code"] == muscle.code
        assert body["title"] == "Placement biceps"

    def test_muscle_without_guide_404(self, client):
        user = UserFactory()
        muscle = MuscleFactory()
        response = client.get(f"/api/v1/muscles/{muscle.pk}/placement-guide/", **auth_headers(user))
        assert response.status_code == 404

    def test_unknown_muscle_404(self, client):
        user = UserFactory()
        response = client.get(
            f"/api/v1/muscles/{uuid.uuid4()}/placement-guide/", **auth_headers(user)
        )
        assert response.status_code == 404
