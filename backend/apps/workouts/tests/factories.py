"""Factories de test de la feature 05 (app ``workouts``).

Usage : ``from apps.workouts.tests.factories import WorkoutFactory, WorkoutExerciseFactory``.
"""

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.exercises.tests.factories import ExerciseFactory
from apps.workouts.models import Workout, WorkoutExercise


class WorkoutFactory(DjangoModelFactory):
    """Plan d'entraînement ; ``athlete`` nullable (plan personnel sans profil)."""

    class Meta:
        model = Workout

    owner = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Plan {n}")
    athlete = None
    notes = ""


class WorkoutExerciseFactory(DjangoModelFactory):
    """Ligne ordonnée d'un plan (``order`` 1-based, unique par plan)."""

    class Meta:
        model = WorkoutExercise

    workout = factory.SubFactory(WorkoutFactory)
    exercise = factory.SubFactory(ExerciseFactory)
    order = 1
    target_sets = 3
    target_reps = 10
    parameters = {}
