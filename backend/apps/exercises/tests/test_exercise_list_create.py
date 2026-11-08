"""Tests de l'API exercices : ``GET/POST /api/v1/exercises/``.

Matrice global × personnel × rôles (spec feature 05) :
- un exercice GLOBAL est lisible par tout utilisateur authentifié ;
- un exercice PERSONNEL n'est visible que par son créateur (404 pour les
  autres — l'existence n'est pas révélée) ;
- la création déduit ``is_global`` du statut « staff » (``is_staff`` ou
  superuser → bibliothèque globale, sinon personnel) puis le gèle :
  ``is_global`` n'est jamais un champ d'entrée ;
- filtres : global/personnel, archivé, type de mouvement, groupe musculaire ;
  recherche texte sur nom et description.
"""

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.exercises.models import Exercise, MuscleGroup
from apps.exercises.tests.factories import (
    ExerciseFactory,
    ExerciseMuscleFactory,
    MuscleFactory,
)


class TestExerciseList:
    def test_anonymous_refused(self, client):
        assert client.get("/api/v1/exercises/").status_code == 401

    def test_user_sees_global_and_own_personal_only(self, client):
        """Matrice de base : globaux + personnels du connecté, jamais les tiers."""
        user = UserFactory()
        global_exercise = ExerciseFactory(is_global=True, created_by=UserFactory())
        own_personal = ExerciseFactory(created_by=user)
        other_personal = ExerciseFactory()  # personnel d'un tiers : invisible
        response = client.get("/api/v1/exercises/", **auth_headers(user))
        assert response.status_code == 200
        ids = {e["id"] for e in response.json()["results"]}
        expected = set(Exercise.objects.filter(is_global=True).values_list("pk", flat=True))
        expected.add(own_personal.pk)
        assert ids == {str(pk) for pk in expected}
        assert str(global_exercise.pk) in ids
        assert str(other_personal.pk) not in ids

    def test_superuser_sees_everything(self, client):
        """Le superuser voit les globaux ET tous les personnels (modération)."""
        superuser = UserFactory(is_superuser=True)
        personal_1 = ExerciseFactory()
        personal_2 = ExerciseFactory()
        response = client.get("/api/v1/exercises/", **auth_headers(superuser))
        assert response.status_code == 200
        ids = {e["id"] for e in response.json()["results"]}
        assert str(personal_1.pk) in ids
        assert str(personal_2.pk) in ids
        assert len(ids) == Exercise.objects.count()

    def test_creator_identity_never_exposed(self, client):
        """Ni email ni pk du créateur dans la réponse (privacy by default)."""
        user = UserFactory()
        ExerciseFactory(created_by=user)
        response = client.get("/api/v1/exercises/", **auth_headers(user))
        for exercise in response.json()["results"]:
            assert "created_by" not in exercise
            assert "owner" not in exercise
            assert "email" not in exercise

    def test_filter_is_global(self, client):
        user = UserFactory()
        global_exercise = ExerciseFactory(is_global=True)
        personal = ExerciseFactory(created_by=user)  # personnel : exclu par le filtre
        response = client.get("/api/v1/exercises/?is_global=true", **auth_headers(user))
        ids = {e["id"] for e in response.json()["results"]}
        expected = set(Exercise.objects.filter(is_global=True).values_list("pk", flat=True))
        assert ids == {str(pk) for pk in expected}
        assert str(global_exercise.pk) in ids
        assert str(personal.pk) not in ids

    def test_filter_is_archived(self, client):
        user = UserFactory()
        archived = ExerciseFactory(created_by=user, is_archived=True)
        ExerciseFactory(created_by=user)
        response = client.get("/api/v1/exercises/?is_archived=true", **auth_headers(user))
        assert [e["id"] for e in response.json()["results"]] == [str(archived.pk)]

    def test_filter_movement_type(self, client):
        user = UserFactory()
        isometric = ExerciseFactory(created_by=user, movement_type=Exercise.MovementType.ISOMETRIC)
        compound = ExerciseFactory(created_by=user, movement_type=Exercise.MovementType.COMPOUND)
        response = client.get(
            "/api/v1/exercises/?movement_type=isometric", **auth_headers(user)
        )
        ids = {e["id"] for e in response.json()["results"]}
        expected = set(
            Exercise.objects.filter(movement_type=Exercise.MovementType.ISOMETRIC).values_list(
                "pk", flat=True
            )
        )
        assert ids == {str(pk) for pk in expected}
        assert str(isometric.pk) in ids
        assert str(compound.pk) not in ids

    def test_filter_by_muscle_group(self, client):
        user = UserFactory()
        group = MuscleGroup.objects.get(code="chest")
        linked = ExerciseFactory(created_by=user)
        ExerciseMuscleFactory(exercise=linked, muscle=MuscleFactory(muscle_group=group))
        other = ExerciseFactory(
            created_by=user,
        )  # muscle d'un autre groupe : exclu par le filtre
        ExerciseMuscleFactory(exercise=other, muscle=MuscleFactory())
        response = client.get(
            f"/api/v1/exercises/?muscles__muscle_group={group.pk}", **auth_headers(user)
        )
        ids = {e["id"] for e in response.json()["results"]}
        expected = set(
            Exercise.objects.filter(muscles__muscle_group=group).values_list("pk", flat=True)
        )
        assert ids == {str(pk) for pk in expected}
        assert str(linked.pk) in ids
        assert str(other.pk) not in ids

    def test_text_search_on_name_and_description(self, client):
        user = UserFactory()
        by_name = ExerciseFactory(created_by=user, name="Rowing Machine Special")
        by_description = ExerciseFactory(
            created_by=user, description="Travail du serrant antérieur"
        )
        ExerciseFactory(created_by=user)
        response = client.get("/api/v1/exercises/?search=serrant", **auth_headers(user))
        assert [e["id"] for e in response.json()["results"]] == [str(by_description.pk)]
        response = client.get("/api/v1/exercises/?search=Rowing", **auth_headers(user))
        assert [e["id"] for e in response.json()["results"]] == [str(by_name.pk)]


class TestExerciseCreate:
    def test_anonymous_cannot_create(self, client):
        response = post_json(client, "/api/v1/exercises/", {"name": "Nope"})
        assert response.status_code == 401

    def test_non_staff_creates_personal_exercise(self, client):
        user = UserFactory()
        response = post_json(
            client, "/api/v1/exercises/", {"name": "Mon exercice perso"}, **auth_headers(user)
        )
        assert response.status_code == 201, response.data
        body = response.json()
        assert body["is_global"] is False
        assert Exercise.objects.get(pk=body["id"]).created_by_id == user.pk

    def test_staff_creates_global_exercise(self, client):
        staff = UserFactory(is_staff=True)
        response = post_json(
            client, "/api/v1/exercises/", {"name": "Exercice du staff"}, **auth_headers(staff)
        )
        assert response.status_code == 201, response.data
        assert response.json()["is_global"] is True

    def test_superuser_creates_global_exercise(self, client):
        superuser = UserFactory(is_superuser=True)
        response = post_json(
            client, "/api/v1/exercises/", {"name": "Exercice super"}, **auth_headers(superuser)
        )
        assert response.json()["is_global"] is True

    def test_is_global_input_ignored_for_non_staff(self, client):
        """``is_global`` n'est jamais un champ d'entrée : un non-staff reste personnel."""
        user = UserFactory()
        response = post_json(
            client,
            "/api/v1/exercises/",
            {"name": "Tentative globale", "is_global": True},
            **auth_headers(user),
        )
        assert response.status_code == 201
        assert response.json()["is_global"] is False

    def test_creates_with_muscle_links_and_roles(self, client):
        user = UserFactory()
        muscle = MuscleFactory()
        payload = {
            "name": "Exercice musclé",
            "muscles": [{"muscle": str(muscle.pk), "role": "secondary"}],
        }
        response = post_json(client, "/api/v1/exercises/", payload, **auth_headers(user))
        assert response.status_code == 201, response.data
        exercise = Exercise.objects.get(pk=response.json()["id"])
        link = exercise.muscle_links.get()
        assert link.muscle_id == muscle.pk
        assert link.role == "secondary"

    def test_duplicate_muscle_in_payload_refused(self, client):
        user = UserFactory()
        muscle = MuscleFactory()
        payload = {
            "name": "Doublon",
            "muscles": [
                {"muscle": str(muscle.pk), "role": "primary"},
                {"muscle": str(muscle.pk), "role": "secondary"},
            ],
        }
        response = post_json(client, "/api/v1/exercises/", payload, **auth_headers(user))
        assert response.status_code == 400

    def test_missing_name_refused(self, client):
        user = UserFactory()
        response = post_json(client, "/api/v1/exercises/", {}, **auth_headers(user))
        assert response.status_code == 400
