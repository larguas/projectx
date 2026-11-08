"""Couche de services de la feature 05 (app ``exercises``).

Règles :
- création : ``is_global`` est déduit du statut « staff » de l'utilisateur
  (staff → bibliothèque globale, sinon personnel) puis gelé — cf. docstring
  de ``apps.exercises.selectors.is_staff`` ; le créateur est toujours tracé
  (``created_by``, même pour les exercices globaux, à des fins d'audit) ;
- mise à jour : autorisée par ``selectors.can_write_exercise`` (global →
  staff uniquement ; personnel → créateur uniquement) ; la liste ``muscles``,
  quand elle est fournie, remplace intégralement les liens existants ;
- suppression : un exercice PERSONNEL est supprimé physiquement par son
  créateur (ses lignes de plans sont retirées en cascade — seuls ses plans
  pouvaient y référencer un exercice personnel) ; un exercice GLOBAL n'est
  JAMAIS supprimé physiquement par l'API : le DELETE l'archive logiquement
  (``is_archived=True``), pour ne jamais retirer silencieusement des lignes
  des plans d'autres utilisateurs.

Les erreurs lèvent ``ExercisesServiceError`` avec un code stable mappé en
HTTP par les vues (``forbidden`` -> 403). Les cas « non lisible » sont gérés
en amont par les vues (404 — l'existence n'est pas révélée, même convention
que la feature 04).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.exercises.models import Exercise


class ExercisesServiceError(Exception):
    """Erreur métier des services exercises ; ``code`` est le code stable de l'API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _set_muscle_links(exercise: Exercise, entries: list) -> None:
    """Remplace intégralement les liens muscle/exercice (rôle unique par muscle)."""
    from apps.exercises.models import ExerciseMuscle

    exercise.muscle_links.all().delete()
    for entry in entries:
        ExerciseMuscle.objects.create(
            exercise=exercise,
            muscle=entry["muscle"],
            role=entry.get("role", ExerciseMuscle.Role.PRIMARY),
        )


def create_exercise(user, data: dict) -> Exercise:
    """Crée un exercice pour ``user`` (global si staff, personnel sinon).

    ``data`` contient les champs validés par ``CreateExerciseSerializer``.
    """
    from apps.exercises import selectors
    from apps.exercises.models import Exercise

    exercise = Exercise.objects.create(
        name=data["name"],
        description=data.get("description", ""),
        movement_type=data.get("movement_type", Exercise.MovementType.COMPOUND),
        default_parameters=data.get("default_parameters") or {},
        is_global=selectors.is_staff(user),
        created_by=user,
    )
    _set_muscle_links(exercise, data.get("muscles") or [])
    return exercise


def update_exercise(user, exercise: Exercise, data: dict) -> Exercise:
    """Met à jour un exercice ; autorisée par ``selectors.can_write_exercise``."""
    from apps.exercises import selectors

    if not selectors.can_write_exercise(user, exercise):
        raise ExercisesServiceError(
            "forbidden",
            "Vous ne pouvez pas modifier cet exercice (exercice global : staff "
            "uniquement ; exercice personnel : créateur uniquement).",
        )
    for field in ("name", "description", "movement_type", "default_parameters", "is_archived"):
        if field in data:
            setattr(exercise, field, data[field])
    exercise.save()
    if "muscles" in data:
        _set_muscle_links(exercise, data["muscles"])
    return exercise


def delete_or_archive_exercise(user, exercise: Exercise) -> Exercise | None:
    """Supprime (personnel) ou archive logiquement (global) un exercice.

    Retourne l'exercice archivé, ou ``None`` s'il a été supprimé physiquement.
    """
    from apps.exercises import selectors

    if not selectors.can_write_exercise(user, exercise):
        raise ExercisesServiceError(
            "forbidden",
            "Vous ne pouvez pas supprimer cet exercice (exercice global : staff "
            "uniquement ; exercice personnel : créateur uniquement).",
        )
    if exercise.is_global:
        # Bibliothèque partagée : jamais de suppression physique par l'API —
        # un DELETE sur un exercice global ne retire pas silencieusement des
        # lignes des plans d'autres utilisateurs.
        exercise.is_archived = True
        exercise.save(update_fields=["is_archived", "updated_at"])
        return exercise
    exercise.delete()
    return None
