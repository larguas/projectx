"""Modèles de la feature 05 (app ``workouts``).

- ``Workout`` : plan d'entraînement nommé, appartenant à un utilisateur
  (``owner``) et éventuellement rattaché au profil sportif d'un athlète
  (``athlete``, nullable — un plan personnel sans profil sportif reste
  possible, cas « propriétaire sans profil » identique à la feature 04).
- ``WorkoutExercise`` : ligne ordonnée du plan (``order`` 1..N, unique par
  plan) associant un exercice à ses cibles (séries / reps) et paramètres.

L'ordre est une donnée métier : la liste est remplacée de façon atomique via
``PUT /api/v1/workouts/{id}/exercises/`` (les lignes sont réindexées 1..N).
"""

from django.conf import settings
from django.db import models

from core.models import TimestampedModel, UUIDModel


class Workout(TimestampedModel, UUIDModel):
    """Plan d'entraînement.

    ``owner`` est l'utilisateur qui a créé le plan : seul lui (ou un lecteur
    autorisé via ``core.access``, cf. ``apps.workouts.selectors``) peut y
    accéder. ``athlete`` est le profil sportif concerné — nullable : un plan
    sans athlète n'est accessible que par son propriétaire (un coach ne peut
    pas « adopter » un plan orphelin, même avec un grant actif).

    ``athlete`` est en ``PROTECT`` : la suppression d'un profil sportif est
    refusée tant qu'il existe des plans qui y sont rattachés (les plans ont de
    la valeur métier ; on ne supprime jamais silencieusement un historique).
    """

    name = models.CharField("nom", max_length=200)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="propriétaire",
        on_delete=models.CASCADE,
        related_name="workouts",
    )
    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        verbose_name="sportif",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="workouts",
    )
    notes = models.TextField("notes", blank=True)

    class Meta:
        verbose_name = "entraînement"
        verbose_name_plural = "entraînements"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.name


class WorkoutExercise(TimestampedModel, UUIDModel):
    """Ligne d'un plan : un exercice ordonné avec ses cibles.

    ``order`` est 1-based et UNIQUE par plan (contrainte en base) — deux
    lignes ne peuvent pas partager la même position. La validation de
    l'ordre est portée par :
    - la contrainte ``unique_order_per_workout`` (filet de sécurité base) ;
    - le service ``workouts.services.replace_workout_exercises`` qui réindexe
      la liste 1..N et refuse les exercices en double dans la demande.

    ``exercise`` est en ``CASCADE`` : la suppression d'un exercice personnel
    retire les lignes des plans de son créateur (seul celui-ci pouvait y
    référencer un exercice personnel, cf. visibilité de la feature 05).
    """

    workout = models.ForeignKey(
        Workout,
        verbose_name="entraînement",
        on_delete=models.CASCADE,
        related_name="exercises",
    )
    exercise = models.ForeignKey(
        "exercises.Exercise",
        verbose_name="exercice",
        on_delete=models.CASCADE,
        related_name="workout_lines",
    )
    order = models.PositiveIntegerField("ordre", help_text="Position 1-based dans le plan.")
    target_sets = models.PositiveIntegerField("séries cibles")
    target_reps = models.PositiveIntegerField("reps cibles")
    parameters = models.JSONField(
        "paramètres",
        default=dict,
        help_text='JSON : tempo, repos, notes par exercice… (ex. {"tempo": "3-1-2"}).',
    )

    class Meta:
        verbose_name = "exercice d'un entraînement"
        verbose_name_plural = "exercices des entraînements"
        ordering = ("workout_id", "order")
        constraints = [
            models.UniqueConstraint(fields=("workout", "order"), name="unique_order_per_workout")
        ]

    def __str__(self) -> str:
        return f"{self.workout} #{self.order} : {self.exercise}"
