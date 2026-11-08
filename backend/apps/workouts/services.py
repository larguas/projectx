"""Couche de services de la feature 05 (app ``workouts``).

Règles :
- le créateur d'un plan en est le propriétaire ; seuls le propriétaire ou un
  porteur d'un grant ACTIF portant le scope ``sessions:write`` sur le sportif
  rattaché peuvent modifier un plan (PATCH/DELETE/remplacement des exercices)
  — vérifié via ``apps.workouts.selectors.can_write_workout``, qui délègue à
  ``core.access`` (aucune requête directe sur les grants ici, décision n°8) ;
- rattacher un plan à un sportif exige l'accès en écriture à ce sportif
  (profil propre, superutilisateur ou grant ``sessions:write`` actif) : sans
  cette règle, n'importe quel utilisateur pourrait « injecter » des plans
  dans la vue d'un coach tiers (la liste des workouts inclut les plans de ses
  sportifs) ;
- le remplacement de la liste ordonnée d'exercices est ATOMIQUE (transaction)
  et réindexe 1..N ; chaque exercice référencé doit être VISIBLE par le
  demandeur (global ou personnel du demandeur) — sinon on laisserait fuiter
  l'existence d'un exercice personnel via les lignes d'un plan ;
- ``DELETE /api/v1/workouts/{id}/`` supprime physiquement le plan et ses
  lignes : contrairement aux capteurs (feature 04), un plan n'a pas
  d'historique de données ingérées à préserver en feature 05.

Les erreurs lèvent ``WorkoutsServiceError`` avec un code stable mappé en HTTP
par les vues (``forbidden`` -> 403). Les cas « non lisible » sont gérés en
amont par les vues (404 — l'existence n'est pas révélée, même convention que
la feature 04).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.workouts.models import Workout


class WorkoutsServiceError(Exception):
    """Erreur métier des services workouts ; ``code`` est le code stable de l'API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _assert_athlete_write_access(user, athlete) -> None:
    """Rattachement à un sportif : accès ``sessions:write`` requis (core.access)."""
    from core import access, scopes

    if athlete is None:
        return
    if not access.can_access_athlete(user, athlete, scopes.SESSIONS_WRITE.name):
        raise WorkoutsServiceError(
            "forbidden",
            "Vous n'avez pas le droit de rattacher ce plan à ce sportif.",
        )


def create_workout(user, data: dict) -> Workout:
    """Crée un plan pour ``user`` (``owner = user``).

    ``data`` contient les champs validés par ``CreateWorkoutSerializer``
    (``name``, ``athlete`` nullable, ``notes``).
    """
    from apps.workouts.models import Workout

    _assert_athlete_write_access(user, data.get("athlete"))
    return Workout.objects.create(
        name=data["name"], owner=user, athlete=data.get("athlete"), notes=data.get("notes", "")
    )


def update_workout(user, workout: Workout, data: dict) -> Workout:
    """Met à jour un plan ; écriture selon ``selectors.can_write_workout``.

    Si l'attachement change vers un autre sportif, l'accès en écriture à ce
    nouvel athlète est exigé (même règle qu'à la création). Remettre
    ``athlete`` à ``None`` est autorisé : le plan redevient alors accessible
    au propriétaire uniquement.
    """
    from apps.workouts import selectors

    if not selectors.can_write_workout(user, workout):
        raise WorkoutsServiceError(
            "forbidden",
            "Vous ne pouvez pas modifier ce plan (propriétaire ou grant "
            "« sessions:write » actif sur le sportif rattaché).",
        )
    new_athlete = data.get("athlete")
    if "athlete" in data and new_athlete is not None and new_athlete.pk != workout.athlete_id:
        _assert_athlete_write_access(user, new_athlete)
    for field in ("name", "athlete", "notes"):
        if field in data:
            setattr(workout, field, data[field])
    workout.save()
    return workout


def delete_workout(user, workout: Workout) -> None:
    """Supprime physiquement un plan et ses lignes (pas d'historique à garder)."""
    from apps.workouts import selectors

    if not selectors.can_write_workout(user, workout):
        raise WorkoutsServiceError(
            "forbidden",
            "Vous ne pouvez pas supprimer ce plan (propriétaire ou grant "
            "« sessions:write » actif sur le sportif rattaché).",
        )
    workout.delete()


def replace_workout_exercises(user, workout: Workout, entries: list) -> list:
    """Remplace ATOMIQUEMENT la liste ordonnée d'exercices d'un plan.

    ``entries`` est la liste complète validée par
    ``ReplaceWorkoutExercisesSerializer`` (doublons déjà refusés) : les lignes
    existantes sont supprimées puis recréées avec ``order`` 1..N dans une
    transaction — un échec intermédiaire ne laisse jamais un plan partiel.

    Chaque exercice référencé doit être visible par le demandeur (global, ou
    personnel du demandeur) : sinon l'existence d'un exercice personnel
    d'autrui fuirait via les lignes du plan.
    """
    from django.db import transaction

    from apps.exercises import selectors as exercise_selectors
    from apps.workouts import selectors
    from apps.workouts.models import WorkoutExercise

    if not selectors.can_write_workout(user, workout):
        raise WorkoutsServiceError(
            "forbidden",
            "Vous ne pouvez pas modifier les exercices de ce plan (propriétaire "
            "ou grant « sessions:write » actif sur le sportif rattaché).",
        )
    visible_ids = set(exercise_selectors.visible_exercises(user).values_list("pk", flat=True))
    for entry in entries:
        if entry["exercise"].pk not in visible_ids:
            raise WorkoutsServiceError(
                "forbidden",
                "Vous ne pouvez pas référencer un exercice qui ne vous est pas visible.",
            )
    with transaction.atomic():
        workout.exercises.all().delete()
        lines = [
            WorkoutExercise(
                workout=workout,
                exercise=entry["exercise"],
                order=index,
                target_sets=entry["target_sets"],
                target_reps=entry["target_reps"],
                parameters=entry.get("parameters") or {},
            )
            for index, entry in enumerate(entries, start=1)
        ]
        WorkoutExercise.objects.bulk_create(lines)
    return list(workout.exercises.order_by("order"))
