"""Factories de test de la feature 05 (app ``exercises``).

Usage : ``from apps.exercises.tests.factories import ExerciseFactory, …``.

Les factories créent des données HORS seed (codes/noms séquentiels) ; les
données seedées par la migration 0003 restent accessibles via leurs codes
stables (cf. ``apps.exercises.migrations.0003_seed_library_v1``).
"""

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.exercises.models import Exercise, ExerciseMuscle, Muscle, MuscleGroup


class MuscleGroupFactory(DjangoModelFactory):
    """Groupe musculaire fictif (hors catalogue seedé)."""

    class Meta:
        model = MuscleGroup

    code = factory.Sequence(lambda n: f"group_test_{n}")
    name = factory.Sequence(lambda n: f"Groupe test {n}")
    body_region = "trunk"


class MuscleFactory(DjangoModelFactory):
    """Muscle fictif rattaché à un groupe."""

    class Meta:
        model = Muscle

    code = factory.Sequence(lambda n: f"muscle_test_{n}")
    name = factory.Sequence(lambda n: f"Muscle test {n}")
    latin_name = None
    muscle_group = factory.SubFactory(MuscleGroupFactory)
    region = "zone de test"
    side_relevant = True


class ExerciseFactory(DjangoModelFactory):
    """Exercice PERSONNEL par défaut (``is_global=False``, créateur fictif)."""

    class Meta:
        model = Exercise

    name = factory.Sequence(lambda n: f"Exercice test {n}")
    description = "Description de test."
    movement_type = Exercise.MovementType.COMPOUND
    default_parameters = {"target_reps": 10}
    is_global = False
    created_by = factory.SubFactory(UserFactory)
    is_archived = False


class ExerciseMuscleFactory(DjangoModelFactory):
    """Lien exercice/muscle avec rôle."""

    class Meta:
        model = ExerciseMuscle

    exercise = factory.SubFactory(ExerciseFactory)
    muscle = factory.SubFactory(MuscleFactory)
    role = ExerciseMuscle.Role.PRIMARY
