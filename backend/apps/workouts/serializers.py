"""Sérialiseurs de la feature 05 (app ``workouts``).

Règles d'exposition :
- l'identité du propriétaire n'est JAMAIS exposée sur un plan (ni email ni
  pk) : un coach qui lit les plans d'un sportif via un grant actif ne reçoit
  que le nom, les notes et les lignes du plan ;
- ``athlete`` est une référence compacte (``id`` + ``sport``) : pas d'email,
  même pour le propriétaire (convention « données privées par défaut ») ;
- les exercices des lignes de plan sont des références compactes (``id``,
  ``name``, ``movement_type``) : la lecture d'un plan ne révèle jamais le
  contenu complet d'un exercice (description, paramètres par défaut, muscles)
  — en particulier pas celui d'un exercice personnel référencé par son auteur ;
- ``editable`` est calculé pour l'utilisateur courant (propriétaire, ou grant
  ``sessions:write`` actif sur le sportif rattaché) : le client sait s'il peut
  PATCH/DELETE/remplacer les exercices sans deviner ses droits.

Écriture :
- ``CreateWorkoutSerializer`` / ``UpdateWorkoutSerializer`` portent les champs
  du plan (``name``, ``athlete``, ``notes``) ; l'attachement à un sportif est
  contrôlé en service par ``core.access`` (scope ``sessions:write`` — un plan
  rattaché à un sportif est une donnée d'entraînement de ce sportif) ;
- ``WorkoutExerciseInputSerializer`` porte une ligne du remplacement ordonné
  (``PUT /api/v1/workouts/{id}/exercises/``) : un même exercice ne peut pas
  apparaître deux fois dans la liste.
"""

from rest_framework import serializers

from apps.athletes.models import AthleteProfile
from apps.exercises.models import Exercise
from apps.workouts.models import Workout, WorkoutExercise


class AthleteReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un profil sportif (``id`` + ``sport``)."""

    class Meta:
        model = AthleteProfile
        fields = ("id", "sport")
        read_only_fields = fields


class ExerciseReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un exercice dans une ligne de plan.

    Seuls ``id``, ``name`` et ``movement_type`` : le reste du contenu
    (description, muscles, paramètres par défaut) ne fuit pas via un plan —
    un exercice personnel référencé par son auteur y compris.
    """

    class Meta:
        model = Exercise
        fields = ("id", "name", "movement_type")
        read_only_fields = fields


class WorkoutExerciseSerializer(serializers.ModelSerializer):
    """Ligne d'un plan (lecture) : exercice en référence compacte."""

    exercise = ExerciseReferenceSerializer(read_only=True)

    class Meta:
        model = WorkoutExercise
        fields = ("id", "exercise", "order", "target_sets", "target_reps", "parameters")
        read_only_fields = fields


class WorkoutSerializer(serializers.ModelSerializer):
    """Plan d'entraînement (lecture) ; ``editable`` est calculé pour le courant."""

    athlete = AthleteReferenceSerializer(read_only=True)
    exercises = WorkoutExerciseSerializer(many=True, read_only=True)
    editable = serializers.SerializerMethodField()

    class Meta:
        model = Workout
        fields = (
            "id",
            "name",
            "athlete",
            "notes",
            "exercises",
            "editable",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "athlete",
            "exercises",
            "editable",
            "created_at",
            "updated_at",
        )

    def get_editable(self, obj) -> bool:
        from apps.workouts import selectors

        request = self.context.get("request")
        user = getattr(request, "user", None) if request is not None else None
        return selectors.can_write_workout(user, obj)


class CreateWorkoutSerializer(serializers.Serializer):
    """Création d'un plan (``POST /api/v1/workouts/``).

    ``athlete`` est optionnel : un plan sans sportif reste accessible à son
    propriétaire uniquement. Quand il est fourni, l'attachement est contrôlé
    en service par ``core.access`` avec le scope ``sessions:write`` (un plan
    rattaché à un sportif est une donnée d'entraînement de ce sportif — on ne
    peut pas « injecter » un plan dans la vue d'un coach tiers).
    """

    name = serializers.CharField(max_length=200)
    athlete = serializers.PrimaryKeyRelatedField(
        queryset=AthleteProfile.objects.all(), required=False, allow_null=True, default=None
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class UpdateWorkoutSerializer(serializers.Serializer):
    """Mise à jour partielle (``PATCH /api/v1/workouts/{id}/``).

    Tous les champs sont optionnels. ``athlete`` peut être remis à ``null``
    pour détacher un plan de son sportif (le plan redevient alors accessible
    au propriétaire uniquement) ; le changement d'attachement est contrôlé en
    service par ``core.access`` (scope ``sessions:write`` sur le nouveau
    sportif). Les exercices du plan ne se modifient PAS ici : seul
    ``PUT /api/v1/workouts/{id}/exercises/`` remplace la liste ordonnée.
    """

    name = serializers.CharField(max_length=200, required=False)
    athlete = serializers.PrimaryKeyRelatedField(
        queryset=AthleteProfile.objects.all(), required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_blank=True)


class WorkoutExerciseInputSerializer(serializers.Serializer):
    """Une entrée de la liste ordonnée du remplacement d'exercices.

    ``exercise`` est une pk UUID ; la visibilité de l'exercice pour le
    demandeur (global ou personnel du demandeur) est contrôlée en service —
    référencer un exercice invisible serait une fuite de son existence via
    les lignes du plan.
    """

    exercise = serializers.PrimaryKeyRelatedField(queryset=Exercise.objects.all())
    target_sets = serializers.IntegerField(min_value=1)
    target_reps = serializers.IntegerField(min_value=1)
    parameters = serializers.JSONField(required=False, default=dict)


def _validate_exercise_entries(value: list) -> list:
    """Un même exercice ne peut pas apparaître deux fois dans un plan."""
    seen: set = set()
    for entry in value:
        exercise_id = entry["exercise"].pk
        if exercise_id in seen:
            raise serializers.ValidationError(
                "Un même exercice ne peut apparaître qu'une fois dans le plan."
            )
        seen.add(exercise_id)
    return value


class ReplaceWorkoutExercisesSerializer(serializers.Serializer):
    """Remplacement de la liste ordonnée d'un plan (``PUT .../exercises/``).

    ``exercises`` est la liste COMPLÈTE des lignes, dans l'ordre souhaité :
    le service réindexe 1..N et remplace atomiquement les lignes existantes.
    Une liste vide est autorisée (plan sans exercice).
    """

    exercises = WorkoutExerciseInputSerializer(many=True, required=False, default=list)

    def validate_exercises(self, value: list) -> list:
        return _validate_exercise_entries(value)
