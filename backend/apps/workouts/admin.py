"""Admin Django de la feature 05 (app ``workouts``).

Les plans sont listés pour l'exploitation ; les lignes ordonnées se gèrent en
inline (l'ordre est une donnée métier : le remplacement atomique passe par
l'API, cf. ``apps.workouts.services.replace_workout_exercises``). L'identité
des utilisateurs n'est exposée que sous forme d'email (convention admin).
"""

from django.contrib import admin

from apps.workouts.models import Workout, WorkoutExercise


class WorkoutExerciseInline(admin.TabularInline):
    """Lignes ordonnées d'un plan (``order`` 1..N, unique par plan)."""

    model = WorkoutExercise
    extra = 0


@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    """Plans d'entraînement."""

    list_display = ("id", "name", "owner_email", "athlete", "created_at")
    search_fields = ("name", "owner__email", "athlete__user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [WorkoutExerciseInline]

    @admin.display(description="Email du propriétaire")
    def owner_email(self, obj) -> str:
        return obj.owner.email


@admin.register(WorkoutExercise)
class WorkoutExerciseAdmin(admin.ModelAdmin):
    """Lignes de plan (consultation directe)."""

    list_display = ("id", "workout", "exercise", "order", "target_sets", "target_reps")
    search_fields = ("workout__name", "exercise__name")
    readonly_fields = ("id", "created_at", "updated_at")
