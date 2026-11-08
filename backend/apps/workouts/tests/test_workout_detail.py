"""Tests de l'API entraînements : ``GET/PATCH/DELETE /api/v1/workouts/{id}/``.

Le détail est visible selon ``apps.workouts.selectors.can_read_workout``
(404 sinon — l'existence n'est pas révélée, même convention que la feature 04) :
propriétaire, superutilisateur, ou grant ``sessions:read`` actif sur le sportif
rattaché. Toute lecture par un NON-propriétaire est auditée (``workout.viewed``) ;
la lecture du propriétaire ne l'est pas. PATCH/DELETE exigent l'écriture
(propriétaire ou grant ``sessions:write`` actif) ; le DELETE supprime
physiquement le plan et ses lignes (pas d'historique de données à préserver).
"""

import json
import uuid

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.teams.tests.factories import AccessGrantFactory
from apps.workouts.models import Workout, WorkoutExercise
from apps.workouts.tests.factories import WorkoutExerciseFactory, WorkoutFactory

SCOPE_READ = "sessions:read"
SCOPE_WRITE = "sessions:write"


def _patch(client, user, workout_id, payload):
    url = f"/api/v1/workouts/{workout_id}/"
    return client.patch(
        url, data=json.dumps(payload), content_type="application/json", **auth_headers(user)
    )


class TestWorkoutDetailRead:
    def test_anonymous_refused(self, client):
        workout = WorkoutFactory()
        assert client.get(f"/api/v1/workouts/{workout.pk}/").status_code == 401

    def test_owner_reads_own_plan_without_audit(self, client):
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        response = client.get(f"/api/v1/workouts/{workout.pk}/", **auth_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == workout.name
        assert body["editable"] is True
        assert "owner" not in body
        assert not AuditEvent.objects.filter(action="workout.viewed").exists()

    def test_coach_reads_plan_with_read_grant_and_audit(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.get(f"/api/v1/workouts/{workout.pk}/", **auth_headers(coach_user))
        assert response.status_code == 200
        event = AuditEvent.objects.get(action="workout.viewed")
        assert event.actor_id == coach_user.pk
        assert event.athlete_id == athlete_profile.pk
        assert event.target_type == "Workout"
        assert str(event.target_id) == str(workout.pk)

    def test_coach_without_grant_gets_404(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        response = client.get(f"/api/v1/workouts/{workout.pk}/", **auth_headers(coach_user))
        assert response.status_code == 404

    def test_orphan_plan_404_for_coach_with_grant(self, client):
        """Un plan sans athlète reste inaccessible même avec un grant actif."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        orphan = WorkoutFactory(owner=UserFactory())  # athlete=None
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.get(f"/api/v1/workouts/{orphan.pk}/", **auth_headers(coach_user))
        assert response.status_code == 404

    def test_superuser_reads_any_plan(self, client):
        superuser = UserFactory(is_superuser=True)
        workout = WorkoutFactory()
        response = client.get(f"/api/v1/workouts/{workout.pk}/", **auth_headers(superuser))
        assert response.status_code == 200

    def test_unknown_id_404(self, client):
        user = UserFactory()
        response = client.get(f"/api/v1/workouts/{uuid.uuid4()}/", **auth_headers(user))
        assert response.status_code == 404

    def test_lines_expose_compact_exercise_reference_only(self, client):
        """Les lignes ne révèlent que id/nom/type de mouvement de l'exercice."""
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        WorkoutExerciseFactory(workout=workout)
        response = client.get(f"/api/v1/workouts/{workout.pk}/", **auth_headers(owner))
        line = response.json()["exercises"][0]
        assert set(line["exercise"]) == {"id", "name", "movement_type"}
        assert line["order"] == 1


class TestWorkoutPatch:
    def test_anonymous_refused(self, client):
        workout = WorkoutFactory()
        response = client.patch(
            f"/api/v1/workouts/{workout.pk}/",
            data=json.dumps({"name": "Nope"}),
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_owner_updates_name_and_notes(self, client):
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        response = _patch(client, owner, workout.pk, {"name": "V2", "notes": "Repos allongé"})
        assert response.status_code == 200, response.data
        workout.refresh_from_db()
        assert workout.name == "V2"
        assert workout.notes == "Repos allongé"

    def test_read_only_grant_cannot_patch(self, client):
        """Un grant ``sessions:read`` n'ouvre pas l'écriture : 403 (plan visible)."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = _patch(client, coach_user, workout.pk, {"name": "Hacking"})
        assert response.status_code == 403

    def test_write_grant_can_patch(self, client):
        """Écriture = grant ``sessions:write`` (lecture ``sessions:read`` requise pour voir le plan)."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(
            athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_READ, SCOPE_WRITE]
        )
        response = _patch(client, coach_user, workout.pk, {"notes": "Programme semaine 3"})
        assert response.status_code == 200, response.data
        workout.refresh_from_db()
        assert workout.notes == "Programme semaine 3"

    def test_write_only_grant_cannot_read_or_patch(self, client):
        """Un scope ne déborde jamais sur un autre : sans ``sessions:read``, 404."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_WRITE])
        assert client.get(f"/api/v1/workouts/{workout.pk}/", **auth_headers(coach_user)).status_code == 404
        response = _patch(client, coach_user, workout.pk, {"notes": "Sans lecture ?"})
        assert response.status_code == 404

    def test_coach_without_grant_gets_404_on_patch(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        response = _patch(client, coach_user, workout.pk, {"name": "Intrusion"})
        assert response.status_code == 404

    def test_owner_reattaches_plan_to_own_athlete(self, client):
        user = UserFactory()
        workout = WorkoutFactory(owner=user)
        profile = AthleteProfileFactory(user=user)
        response = _patch(client, user, workout.pk, {"athlete": str(profile.pk)})
        assert response.status_code == 200, response.data
        workout.refresh_from_db()
        assert workout.athlete_id == profile.pk

    def test_write_grant_cannot_reattach_to_other_athlete(self, client):
        """Changer l'attachement exige l'écriture sur le NOUVEL athlète."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_a = AthleteProfileFactory()
        athlete_b = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_a.user, athlete=athlete_a)
        AccessGrantFactory(
            athlete=athlete_a, grantee_coach=coach, scopes=[SCOPE_READ, SCOPE_WRITE]
        )
        response = _patch(client, coach_user, workout.pk, {"athlete": str(athlete_b.pk)})
        assert response.status_code == 403
        workout.refresh_from_db()
        assert workout.athlete_id == athlete_a.pk

    def test_owner_detaches_athlete(self, client):
        """Remettre ``athlete`` à None : le plan redevient propriétaire-only."""
        user = UserFactory()
        profile = AthleteProfileFactory(user=user)
        workout = WorkoutFactory(owner=user, athlete=profile)
        response = _patch(client, user, workout.pk, {"athlete": None})
        assert response.status_code == 200, response.data
        workout.refresh_from_db()
        assert workout.athlete_id is None

    def test_missing_name_patch_still_valid(self, client):
        """PATCH partiel : ``name`` absent ne casse pas la mise à jour."""
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        response = _patch(client, owner, workout.pk, {"notes": "Only notes"})
        assert response.status_code == 200
        workout.refresh_from_db()
        assert workout.name != "" and workout.notes == "Only notes"


class TestWorkoutDelete:
    def test_anonymous_refused(self, client):
        workout = WorkoutFactory()
        assert client.delete(f"/api/v1/workouts/{workout.pk}/").status_code == 401

    def test_owner_deletes_physically(self, client):
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        line = WorkoutExerciseFactory(workout=workout)
        response = client.delete(f"/api/v1/workouts/{workout.pk}/", **auth_headers(owner))
        assert response.status_code == 204
        assert not Workout.objects.filter(pk=workout.pk).exists()
        assert not WorkoutExercise.objects.filter(pk=line.pk).exists()

    def test_read_only_grant_cannot_delete(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.delete(f"/api/v1/workouts/{workout.pk}/", **auth_headers(coach_user))
        assert response.status_code == 403
        assert Workout.objects.filter(pk=workout.pk).exists()

    def test_write_grant_can_delete(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(
            athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_READ, SCOPE_WRITE]
        )
        response = client.delete(f"/api/v1/workouts/{workout.pk}/", **auth_headers(coach_user))
        assert response.status_code == 204
        assert not Workout.objects.filter(pk=workout.pk).exists()

    def test_unrelated_user_gets_404_on_delete(self, client):
        other = UserFactory()
        workout = WorkoutFactory()
        response = client.delete(f"/api/v1/workouts/{workout.pk}/", **auth_headers(other))
        assert response.status_code == 404
        assert Workout.objects.filter(pk=workout.pk).exists()
