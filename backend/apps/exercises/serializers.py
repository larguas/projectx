"""Sérialiseurs de la feature 05 (app ``exercises``).

Règles d'exposition :
- les catalogues (``MuscleGroup``, ``Muscle``) sont strictement en lecture
  seule pour les utilisateurs (gestion en admin + seed, cf. modèles) ;
- l'identité du créateur n'est JAMAIS exposée sur un exercice (ni email ni
  pk) : la distinction global/personnel passe par ``is_global``, et un
  exercice personnel d'un tiers est de toute façon invisible (404, cf.
  ``apps.exercises.selectors``) ;
- ``is_global`` n'est jamais un champ d'entrée : il est déduit du statut
  « staff » de l'utilisateur à la création (staff → bibliothèque globale,
  sinon exercice personnel) puis gelé — un exercice ne change pas de nature
  via l'API (cf. docstring de ``apps.exercises.selectors.is_staff``) ;
- ``editable`` est calculé pour l'utilisateur courant : le client sait ainsi
  s'il peut PATCH/DELETE sans deviner ses droits.

Les muscles sont référencés par leur pk UUID ; la liste ``muscles`` d'une
création/mise à jour remplace intégralement les liens existants (rôle unique
par muscle, cf. contrainte ``unique_muscle_per_exercise``).
"""

from rest_framework import serializers

from apps.exercises.models import Exercise, ExerciseMuscle, Muscle, MuscleGroup


class MuscleGroupSerializer(serializers.ModelSerializer):
    """Entrée du catalogue des groupes musculaires (lecture seule)."""

    class Meta:
        model = MuscleGroup
        fields = ("id", "code", "name", "body_region")
        read_only_fields = fields


class MuscleSerializer(serializers.ModelSerializer):
    """Entrée du catalogue des muscles (lecture seule), groupe imbriqué."""

    muscle_group = MuscleGroupSerializer(read_only=True)

    class Meta:
        model = Muscle
        fields = ("id", "code", "name", "latin_name", "muscle_group", "region", "side_relevant")
        read_only_fields = fields


class ExerciseMuscleSerializer(serializers.ModelSerializer):
    """Rôle d'un muscle dans un exercice (lecture, muscle imbriqué)."""

    muscle = MuscleSerializer(read_only=True)

    class Meta:
        model = ExerciseMuscle
        fields = ("id", "muscle", "role")
        read_only_fields = fields


class ExerciseSerializer(serializers.ModelSerializer):
    """Exercice ; ``editable`` est calculé pour l'utilisateur courant."""

    muscles = ExerciseMuscleSerializer(many=True, read_only=True)
    editable = serializers.SerializerMethodField()

    class Meta:
        model = Exercise
        fields = (
            "id",
            "name",
            "description",
            "movement_type",
            "default_parameters",
            "is_global",
            "is_archived",
            "muscles",
            "editable",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "is_global",
            "muscles",
            "editable",
            "created_at",
            "updated_at",
        )

    def get_editable(self, obj) -> bool:
        from apps.exercises import selectors

        request = self.context.get("request")
        user = getattr(request, "user", None) if request is not None else None
        return selectors.can_write_exercise(user, obj)


class ExerciseMuscleInputSerializer(serializers.Serializer):
    """Une entrée de la liste ``muscles`` d'une création/mise à jour."""

    muscle = serializers.PrimaryKeyRelatedField(queryset=Muscle.objects.all())
    role = serializers.ChoiceField(
        choices=ExerciseMuscle.Role.choices, default=ExerciseMuscle.Role.PRIMARY
    )


def _validate_muscle_entries(value: list) -> list:
    """Un même muscle ne peut jouer qu'UN rôle par exercice (unicité)."""
    seen: set = set()
    for entry in value:
        muscle_id = entry["muscle"].pk
        if muscle_id in seen:
            raise serializers.ValidationError(
                "Un même muscle ne peut apparaître qu'une fois (un seul rôle par muscle)."
            )
        seen.add(muscle_id)
    return value


class CreateExerciseSerializer(serializers.Serializer):
    """Création d'un exercice (``POST /api/v1/exercises/``).

    ``is_global`` n'est PAS un champ d'entrée : il est déduit du statut staff
    de l'utilisateur à la création (staff → bibliothèque globale, sinon
    personnel) puis gelé. Un utilisateur non staff ne peut donc créer que des
    exercices personnels ; le staff alimente la bibliothèque partagée.
    """

    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    movement_type = serializers.ChoiceField(
        choices=Exercise.MovementType.choices, default=Exercise.MovementType.COMPOUND
    )
    default_parameters = serializers.JSONField(required=False, default=dict)
    muscles = ExerciseMuscleInputSerializer(many=True, required=False, default=list)

    def validate_muscles(self, value: list) -> list:
        return _validate_muscle_entries(value)


class UpdateExerciseSerializer(serializers.Serializer):
    """Mise à jour partielle (``PATCH /api/v1/exercises/{id}/``).

    Tous les champs sont optionnels ; la liste ``muscles``, quand elle est
    fournie, remplace intégralement les liens existants. ``is_global`` et
    l'identité du créateur ne sont pas modifiables via l'API.
    """

    name = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    movement_type = serializers.ChoiceField(choices=Exercise.MovementType.choices, required=False)
    default_parameters = serializers.JSONField(required=False)
    is_archived = serializers.BooleanField(required=False)
    muscles = ExerciseMuscleInputSerializer(many=True, required=False)

    def validate_muscles(self, value: list) -> list:
        return _validate_muscle_entries(value)
