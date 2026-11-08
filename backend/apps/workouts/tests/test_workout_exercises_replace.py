"""Tests de l'API entraînements : ``PUT /api/v1/workouts/{id}/exercises/``.

Remplacement ATOMIQUE de la liste ordonnée d'exercices d'un plan :
- le corps est ``{"exercises": [...]}`` — liste COMPLÈTE des lignes dans
  l'ordre souhaité ; les lignes existantes sont supprimées puis recréées
  avec ``order`` réindexé 1..N (une liste vide est autorisée) ;
- un même exercice ne peut pas apparaître deux fois (400 en validation) ;
- chaque exercice référencé doit être visible par le demandeur (global ou
  personnel du demandeur) : sinon 403 et AUCUNE ligne n'est modifiée —
  l'existence d'un exercice personnel d'autrui ne fuit pas via un plan ;
- mêmes règles d'accès que le détail du plan : ``sessions:read`` requis pour
  voir le plan (404 sinon), écriture = propriétaire ou grant
  ``sessions:write`` actif sur le sportif rattaché.
"""

import json
import uuid

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.coaches.tests.factories import CoachProfileFactory
from apps.exercises.models import Exercise
from apps.exercises.tests.factories import ExerciseFactory
from apps.teams.tests.factories import AccessGrantFactory
from apps.workouts.models import WorkoutExercise
from apps.workouts.tests.factories import WorkoutExerciseFactory, WorkoutFactory

SCOPE_READ = "sessions:read"
SCOPE_WRITE = "sessions:write"


def _seeded(name: str) -> Exercise:
    """Exercice global seedé par la migration 0003 (nom stable)."""
    return Exercise.objects.get(name=name, is_global=True)


def _entry(exercise: Exercise, sets=3, reps=10, parameters=None) -> dict:
    payload = {"exercise": str(exercise.pk), "target_sets": sets, "target_reps": reps}
    if parameters is not None:
        payload["parameters"] = parameters
    return payload


def _put(client, user, workout_id, entries):
    url = f"/api/v1/workouts/{workout_id}/exercises/"
    return client.put(
        url, data=json.dumps({"exercises": entries}), content_type="application/json", **auth_headers(user)
    )


class TestReplaceAccess:
    def test_anonymous_refused(self, client):
        workout = WorkoutFactory()
        response = client.put(
            f"/api/v1/workouts/{workout.pk}/exercises/",
            data=json.dumps({"exercises": []}),
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_unknown_id_404(self, client):
        user = UserFactory()
        assert _put(client, user, uuid.uuid4(), []).status_code == 404

    def test_unrelated_user_gets_404(self, client):
        """L'existence du plan n'est pas révélée aux non-lisibles."""
        other = UserFactory()
        workout = WorkoutFactory()
        response = _put(client, other, workout.pk, [_entry(_seeded("Bicep Curl"))])
        assert response.status_code == 404

    def test_coach_without_grant_gets_404(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        assert _put(client, coach_user, workout.pk, []).status_code == 404

    def test_read_only_grant_cannot_replace(self, client):
        """Un grant ``sessions:read`` n'ouvre pas l'écriture : 403 (plan visible)."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = _put(client, coach_user, workout.pk, [_entry(_seeded("Bicep Curl"))])
        assert response.status_code == 403

    def test_write_only_grant_cannot_see_plan(self, client):
        """Sans ``sessions:read``, le plan est invisible : 404 (asymétrie documentée)."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_WRITE])
        assert _put(client, coach_user, workout.pk, []).status_code == 404


class TestReplaceSuccess:
    def test_owner_replaces_and_reindexes(self, client):
        """Les lignes existantes sont remplacées ; l'ordre est réindexé 1..N."""
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        old_line = WorkoutExerciseFactory(workout=workout, order=1)
        e1 = _seeded("Bicep Curl")
        e2 = _seeded("Push-Up")
        response = _put(client, owner, workout.pk, [_entry(e2, sets=4), _entry(e1, sets=2)])
        assert response.status_code == 200, response.data
        lines = list(workout.exercises.order_by("order"))
        assert [line.order for line in lines] == [1, 2]
        assert lines[0].exercise_id == e2.pk and lines[0].target_sets == 4
        assert lines[1].exercise_id == e1.pk and lines[1].target_sets == 2
        assert not WorkoutExercise.objects.filter(pk=old_line.pk).exists()
        body = response.json()
        assert [line["order"] for line in body] == [1, 2]
        assert body[0]["exercise"]["id"] == str(e2.pk)

    def test_empty_list_allowed(self, client):
        """Une liste vide vide le plan sans erreur."""
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        WorkoutExerciseFactory(workout=workout)
        response = _put(client, owner, workout.pk, [])
        assert response.status_code == 200, response.data
        assert response.json() == []
        assert not workout.exercises.exists()

    def test_missing_exercises_key_means_empty_list(self, client):
        """Corps ``{}`` : ``exercises`` est optionnel (default=list)."""
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        url = f"/api/v1/workouts/{workout.pk}/exercises/"
        response = client.put(
            url, data=json.dumps({}), content_type="application/json", **auth_headers(owner)
        )
        assert response.status_code == 200
        assert not workout.exercises.exists()

    def test_write_grant_can_replace(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        workout = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(
            athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_READ, SCOPE_WRITE]
        )
        response = _put(client, coach_user, workout.pk, [_entry(_seeded("Bicep Curl"))])
        assert response.status_code == 200, response.data
        assert workout.exercises.count() == 1

    def test_owner_references_own_personal_exercise(self, client):
        """Un exercice personnel du demandeur est visible : référence autorisée."""
        owner = UserFactory()
        personal = ExerciseFactory(created_by=owner)
        workout = WorkoutFactory(owner=owner)
        response = _put(client, owner, workout.pk, [_entry(personal)])
        assert response.status_code == 200, response.data
        assert workout.exercises.get().exercise_id == personal.pk

    def test_parameters_default_to_empty_dict(self, client):
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        response = _put(client, owner, workout.pk, [_entry(_seeded("Bicep Curl"))])
        assert response.status_code == 200
        assert workout.exercises.get().parameters == {}

    def test_parameters_stored(self, client):
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        response = _put(
            client, owner, workout.pk, [_entry(_seeded("Bicep Curl"), parameters={"tempo": "3-1-2"})]
        )
        assert response.status_code == 200
        assert workout.exercises.get().parameters == {"tempo": "3-1-2"}


class TestReplaceValidation:
    def test_duplicate_exercise_rejected(self, client):
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        exercise = _seeded("Bicep Curl")
        response = _put(client, owner, workout.pk, [_entry(exercise), _entry(exercise)])
        assert response.status_code == 400
        assert not workout.exercises.exists()

    def test_missing_target_fields_rejected(self, client):
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        payload = {"exercise": str(_seeded("Bicep Curl").pk)}  # cibles manquantes
        url = f"/api/v1/workouts/{workout.pk}/exercises/"
        response = client.put(
            url, data=json.dumps({"exercises": [payload]}), content_type="application/json", **auth_headers(owner)
        )
        assert response.status_code == 400

    def test_zero_target_reps_rejected(self, client):
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        assert _put(client, owner, workout.pk, [_entry(_seeded("Bicep Curl"), reps=0)]).status_code == 400

    def test_unknown_exercise_id_rejected(self, client):
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        payload = {"exercise": str(uuid.uuid4()), "target_sets": 3, "target_reps": 10}
        url = f"/api/v1/workouts/{workout.pk}/exercises/"
        response = client.put(
            url, data=json.dumps({"exercises": [payload]}), content_type="application/json", **auth_headers(owner)
        )
        assert response.status_code == 400


class TestReplaceVisibility:
    def test_cannot_reference_others_personal_exercise(self, client):
        """Référencer un exercice personnel d'autrui : 403, aucune ligne modifiée."""
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        existing = WorkoutExerciseFactory(workout=workout, order=1)
        invisible = ExerciseFactory(created_by=UserFactory())
        response = _put(client, owner, workout.pk, [_entry(invisible)])
        assert response.status_code == 403
        line = workout.exercises.get()
        assert line.pk == existing.pk
        assert not WorkoutExercise.objects.filter(exercise=invisible).exists()

    def test_rejected_put_leaves_lines_intact(self, client):
        """Un PUT refusé ne laisse jamais un plan partiel : l'ancien état est intact."""
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        e1 = _seeded("Bicep Curl")
        e2 = _seeded("Push-Up")
        line1 = WorkoutExerciseFactory(workout=workout, exercise=e1, order=1, target_sets=3, target_reps=10)
        line2 = WorkoutExerciseFactory(workout=workout, exercise=e2, order=2, target_sets=4, target_reps=8)
        invisible = ExerciseFactory(created_by=UserFactory())
        response = _put(client, owner, workout.pk, [_entry(invisible), _entry(e1)])
        assert response.status_code == 403
        lines = list(workout.exercises.order_by("order"))
        assert [line.pk for line in lines] == [line1.pk, line2.pk]
        assert [(line.order, line.target_sets, line.target_reps) for line in lines] == [
            (1, 3, 10),
            (2, 4, 8),
        ]

    def test_superuser_can_reference_any_exercise(self, client):
        """Un superutilisateur lit tous les exercices : référence autorisée."""
        owner = UserFactory()
        workout = WorkoutFactory(owner=owner)
        personal_of_other = ExerciseFactory(created_by=UserFactory())
        superuser = UserFactory(is_superuser=True)
        response = _put(client, superuser, workout.pk, [_entry(personal_of_other)])
        assert response.status_code == 200, response.data
