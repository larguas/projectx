"""Tests de l'API exercices : ``GET/PATCH/DELETE /api/v1/exercises/{id}/``.

Matrice global × personnel × rôles (spec feature 05) :
- GET : un exercice GLOBAL est lisible par tout utilisateur authentifié ;
  un exercice PERSONNEL n'est visible que par son créateur (ou un superuser,
  cohérence avec la liste) — 404 pour les autres, l'existence n'est pas
  révélée (même convention que la feature 04) ;
- PATCH : global → staff plateforme uniquement (403 sinon, l'exercice étant
  visible) ; personnel → créateur uniquement (404 s'il est invisible, 403
  pour un superuser qui peut lire mais ne modifie pas les données
  personnelles d'autrui — privacy by default) ;
- DELETE : un exercice PERSONNEL est supprimé physiquement par son créateur
  (les lignes de plans le référençant sont retirées en cascade) ; un exercice
  GLOBAL n'est jamais supprimé par l'API : le DELETE l'archive logiquement.
"""

import json
import uuid

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.exercises.models import Exercise
from apps.exercises.tests.factories import (
    ExerciseFactory,
    ExerciseMuscleFactory,
    MuscleFactory,
)


def _patch(client, user, exercise_id, payload):
    url = f"/api/v1/exercises/{exercise_id}/"
    response = client.patch(
        url, data=json.dumps(payload), content_type="application/json", **auth_headers(user)
    )
    return response


class TestExerciseDetailRead:
    def test_anonymous_refused(self, client):
        exercise = ExerciseFactory(is_global=True)
        assert client.get(f"/api/v1/exercises/{exercise.pk}/").status_code == 401

    def test_global_readable_by_any_authenticated_user(self, client):
        user = UserFactory()
        exercise = ExerciseFactory(is_global=True)
        response = client.get(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(user))
        assert response.status_code == 200
        assert response.json()["id"] == str(exercise.pk)

    def test_personal_readable_by_creator(self, client):
        user = UserFactory()
        exercise = ExerciseFactory(created_by=user)
        response = client.get(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(user))
        assert response.status_code == 200
        assert response.json()["is_global"] is False

    def test_personal_invisible_to_other_user(self, client):
        """404 (pas 403) : l'existence d'un exercice personnel n'est pas révélée."""
        other = UserFactory()
        exercise = ExerciseFactory()  # personnel d'un tiers
        response = client.get(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(other))
        assert response.status_code == 404

    def test_personal_invisible_to_staff_non_superuser(self, client):
        """Le staff plateforme ne lit pas les données personnelles d'autrui."""
        staff = UserFactory(is_staff=True)
        exercise = ExerciseFactory()
        response = client.get(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(staff))
        assert response.status_code == 404

    def test_personal_readable_by_superuser(self, client):
        """Accès opérationnel superuser, cohérent avec la liste (tout est visible)."""
        superuser = UserFactory(is_superuser=True)
        exercise = ExerciseFactory()
        response = client.get(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(superuser))
        assert response.status_code == 200

    def test_unknown_id_404(self, client):
        user = UserFactory()
        response = client.get(f"/api/v1/exercises/{uuid.uuid4()}/", **auth_headers(user))
        assert response.status_code == 404

    def test_editable_flag_reflects_rights(self, client):
        user = UserFactory()
        staff = UserFactory(is_staff=True)
        global_exercise = ExerciseFactory(is_global=True)
        personal_exercise = ExerciseFactory(created_by=user)
        body = client.get(f"/api/v1/exercises/{global_exercise.pk}/", **auth_headers(user)).json()
        assert body["editable"] is False
        body = client.get(f"/api/v1/exercises/{global_exercise.pk}/", **auth_headers(staff)).json()
        assert body["editable"] is True
        body = client.get(f"/api/v1/exercises/{personal_exercise.pk}/", **auth_headers(user)).json()
        assert body["editable"] is True


class TestExercisePatch:
    def test_anonymous_refused(self, client):
        exercise = ExerciseFactory(is_global=True)
        response = client.patch(
            f"/api/v1/exercises/{exercise.pk}/",
            data=json.dumps({"name": "Nope"}),
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_staff_updates_global(self, client):
        staff = UserFactory(is_staff=True)
        exercise = ExerciseFactory(is_global=True)
        response = _patch(client, staff, exercise.pk, {"name": "Nouveau nom"})
        assert response.status_code == 200, response.data
        assert response.json()["name"] == "Nouveau nom"
        exercise.refresh_from_db()
        assert exercise.name == "Nouveau nom"

    def test_superuser_updates_global(self, client):
        superuser = UserFactory(is_superuser=True)
        exercise = ExerciseFactory(is_global=True)
        response = _patch(client, superuser, exercise.pk, {"description": "Update"})
        assert response.status_code == 200

    def test_non_staff_cannot_update_global(self, client):
        """Visible mais non modifiable : 403 (pas 404 — l'exercice existe bel et bien)."""
        user = UserFactory()
        exercise = ExerciseFactory(is_global=True)
        response = _patch(client, user, exercise.pk, {"name": "Hacking"})
        assert response.status_code == 403

    def test_creator_updates_personal(self, client):
        user = UserFactory()
        exercise = ExerciseFactory(created_by=user)
        response = _patch(
            client,
            user,
            exercise.pk,
            {"movement_type": Exercise.MovementType.ISOLATION},
        )
        assert response.status_code == 200, response.data
        assert response.json()["movement_type"] == "isolation"

    def test_other_user_cannot_patch_personal(self, client):
        other = UserFactory()
        exercise = ExerciseFactory()
        response = _patch(client, other, exercise.pk, {"name": "Intrusion"})
        assert response.status_code == 404

    def test_superuser_cannot_modify_others_personal(self, client):
        """Lisible par le superuser mais non modifiable : 403 (privacy by default)."""
        superuser = UserFactory(is_superuser=True)
        exercise = ExerciseFactory()
        response = _patch(client, superuser, exercise.pk, {"name": "Trop puissant"})
        assert response.status_code == 403

    def test_patch_replaces_muscle_links_wholesale(self, client):
        user = UserFactory()
        exercise = ExerciseFactory(created_by=user)
        old_muscle = MuscleFactory()
        ExerciseMuscleFactory(exercise=exercise, muscle=old_muscle)
        new_muscle = MuscleFactory()
        response = _patch(
            client,
            user,
            exercise.pk,
            {"muscles": [{"muscle": str(new_muscle.pk), "role": "secondary"}]},
        )
        assert response.status_code == 200, response.data
        links = list(exercise.muscle_links.all())
        assert len(links) == 1
        assert links[0].muscle_id == new_muscle.pk
        assert links[0].role == "secondary"

    def test_patch_is_archived_flag_on_global(self, client):
        staff = UserFactory(is_staff=True)
        exercise = ExerciseFactory(is_global=True)
        response = _patch(client, staff, exercise.pk, {"is_archived": True})
        assert response.status_code == 200
        assert response.json()["is_archived"] is True

    def test_invalid_movement_type_400(self, client):
        user = UserFactory()
        exercise = ExerciseFactory(created_by=user)
        response = _patch(client, user, exercise.pk, {"movement_type": "yoga"})
        assert response.status_code == 400


class TestExerciseDelete:
    def test_anonymous_refused(self, client):
        exercise = ExerciseFactory(is_global=True)
        assert client.delete(f"/api/v1/exercises/{exercise.pk}/").status_code == 401

    def test_creator_deletes_personal_physically(self, client):
        user = UserFactory()
        exercise = ExerciseFactory(created_by=user)
        response = client.delete(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(user))
        assert response.status_code == 204
        assert not Exercise.objects.filter(pk=exercise.pk).exists()

    def test_delete_personal_cascades_workout_lines(self, client):
        """Supprimer un exercice personnel retire ses lignes des plans du créateur."""
        from apps.workouts.models import Workout, WorkoutExercise

        user = UserFactory()
        exercise = ExerciseFactory(created_by=user)
        workout = Workout.objects.create(owner=user, name="Mon plan")
        line = WorkoutExercise.objects.create(
            workout=workout, exercise=exercise, order=1, target_sets=3, target_reps=10
        )
        response = client.delete(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(user))
        assert response.status_code == 204
        assert not Exercise.objects.filter(pk=exercise.pk).exists()
        assert not WorkoutExercise.objects.filter(pk=line.pk).exists()

    def test_other_user_cannot_delete_personal(self, client):
        other = UserFactory()
        exercise = ExerciseFactory()
        response = client.delete(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(other))
        assert response.status_code == 404
        assert Exercise.objects.filter(pk=exercise.pk).exists()

    def test_staff_deletes_global_archives_logically(self, client):
        """Un exercice global n'est JAMAIS supprimé par l'API : archivage logique."""
        staff = UserFactory(is_staff=True)
        exercise = ExerciseFactory(is_global=True)
        response = client.delete(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(staff))
        assert response.status_code == 204
        exercise.refresh_from_db()
        assert exercise.is_archived is True

    def test_superuser_deletes_global_archives_logically(self, client):
        superuser = UserFactory(is_superuser=True)
        exercise = ExerciseFactory(is_global=True)
        response = client.delete(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(superuser))
        assert response.status_code == 204
        assert Exercise.objects.get(pk=exercise.pk).is_archived is True

    def test_non_staff_cannot_delete_global(self, client):
        user = UserFactory()
        exercise = ExerciseFactory(is_global=True)
        response = client.delete(f"/api/v1/exercises/{exercise.pk}/", **auth_headers(user))
        assert response.status_code == 403
        exercise.refresh_from_db()
        assert exercise.is_archived is False
