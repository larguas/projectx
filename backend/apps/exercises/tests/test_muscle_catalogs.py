"""Tests des catalogues ``GET /api/v1/muscle-groups/`` et ``GET /api/v1/muscles/``.

Les catalogues sont en lecture seule pour tout utilisateur authentifié (la
gestion passe par l'admin + le seed). La migration de données 0003 doit avoir
seedé la bibliothèque dans la base de tests : intégrité vérifiée ici
(critère d'acceptation « bibliothèque seedée consultable »).
"""

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers
from apps.exercises.models import Exercise, ExerciseMuscle, Muscle, MuscleGroup


def _seeded(name: str) -> Exercise:
    """Exercice global seedé par la migration 0003 (nom stable)."""
    return Exercise.objects.get(name=name, is_global=True)


class TestMuscleGroupList:
    def test_anonymous_refused(self, client):
        assert client.get("/api/v1/muscle-groups/").status_code == 401

    def test_lists_seeded_groups(self, client):
        user = UserFactory()
        response = client.get("/api/v1/muscle-groups/", **auth_headers(user))
        assert response.status_code == 200
        results = response.json()["results"]
        codes = {g["code"] for g in results}
        # Les 10 groupes du seed (cf. migration 0003).
        assert {
            "shoulder",
            "upper_arm",
            "forearm",
            "chest",
            "back",
            "abdomen",
            "glutes",
            "thigh",
            "calf",
            "shin",
        } <= codes

    def test_group_payload_shape(self, client):
        user = UserFactory()
        response = client.get("/api/v1/muscle-groups/", **auth_headers(user))
        shoulder = next(g for g in response.json()["results"] if g["code"] == "shoulder")
        assert shoulder["name"] == "Épaule"
        assert shoulder["body_region"] == "upper_limb"
        assert set(shoulder) == {"id", "code", "name", "body_region"}


class TestMuscleList:
    def test_anonymous_refused(self, client):
        assert client.get("/api/v1/muscles/").status_code == 401

    def test_lists_seeded_muscles_with_group_nested(self, client):
        user = UserFactory()
        response = client.get("/api/v1/muscles/", **auth_headers(user))
        assert response.status_code == 200
        biceps = next(m for m in response.json()["results"] if m["code"] == "biceps_brachii")
        assert biceps["name"] == "Biceps brachial"
        assert biceps["latin_name"] == "Biceps brachii"
        assert biceps["muscle_group"]["code"] == "upper_arm"
        assert biceps["side_relevant"] is True

    def test_filter_by_muscle_group(self, client):
        user = UserFactory()
        group_pk = MuscleGroup.objects.get(code="thigh").pk
        response = client.get(f"/api/v1/muscles/?muscle_group={group_pk}", **auth_headers(user))
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) > 0
        codes = {m["code"] for m in results}
        assert {"rectus_femoris", "vastus_lateralis", "biceps_femoris"} <= codes
        # Aucun muscle d'un autre groupe ne fuit.
        assert "biceps_brachii" not in codes

    def test_text_search_on_name_latin_and_code(self, client):
        user = UserFactory()
        response = client.get("/api/v1/muscles/?search=gastrocnemius", **auth_headers(user))
        results = response.json()["results"]
        assert {m["code"] for m in results} == {"gastrocnemius"}

    def test_text_search_latin_name(self, client):
        user = UserFactory()
        # « Latissimus » ne correspond qu'au grand dorsal (nom latin).
        response = client.get("/api/v1/muscles/?search=Latissimus", **auth_headers(user))
        assert {m["code"] for m in response.json()["results"]} == {"latissimus_dorsi"}


class TestSeedIntegrity:
    """La migration 0003 doit avoir seedé un catalogue complet et cohérent."""

    def test_seed_counts(self):
        assert MuscleGroup.objects.count() == 10
        assert Muscle.objects.count() == 30
        # 15 exercices globaux seedés (les factories de test n'ont pas tourné ici).
        global_exercises = Exercise.objects.filter(is_global=True)
        assert global_exercises.count() == 15

    def test_every_muscle_belongs_to_a_seeded_group(self):
        for muscle in Muscle.objects.all():
            assert muscle.muscle_group_id is not None

    def test_every_seeded_exercise_has_muscle_links(self):
        for exercise in Exercise.objects.filter(is_global=True):
            assert exercise.muscle_links.count() > 0

    def test_seed_link_count_and_roles(self):
        # 58 liens au total (somme des liens de la migration 0003).
        assert ExerciseMuscle.objects.count() == 58
        biceps = _seeded("Bicep Curl")
        roles = {
            link.muscle.code: link.role for link in biceps.muscle_links.select_related("muscle")
        }
        assert roles == {"biceps_brachii": "primary", "forearm_flexors": "secondary"}

    def test_seed_muscles_reference_only_seeded_groups(self):
        seeded_group_codes = set(MuscleGroup.objects.values_list("code", flat=True))
        for muscle in Muscle.objects.select_related("muscle_group"):
            assert muscle.muscle_group.code in seeded_group_codes
