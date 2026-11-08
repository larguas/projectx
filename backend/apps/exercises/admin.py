"""Admin Django de la feature 05 (app ``exercises``).

Les catalogues (``MuscleGroup``, ``Muscle``) sont strictement en lecture seule
via l'API : leur gestion se fait ici (et par le seed, cf. migration 0003). La
bibliothèque d'exercices est listée pour l'exploitation ; l'archivage logique
d'un exercice global passe par ``is_archived`` (jamais de suppression physique
par l'API, cf. ``apps.exercises.services``).
"""

from django.contrib import admin

from apps.exercises.models import Exercise, ExerciseMuscle, Muscle, MuscleGroup


@admin.register(MuscleGroup)
class MuscleGroupAdmin(admin.ModelAdmin):
    """Catalogue des groupes musculaires."""

    list_display = ("id", "code", "name", "body_region")
    search_fields = ("code", "name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Muscle)
class MuscleAdmin(admin.ModelAdmin):
    """Catalogue des muscles (niveau précis, cf. revue de roadmap)."""

    list_display = ("id", "code", "name", "latin_name", "muscle_group", "region", "side_relevant")
    list_filter = ("muscle_group", "region", "side_relevant")
    search_fields = ("code", "name", "latin_name")
    readonly_fields = ("id", "created_at", "updated_at")


class ExerciseMuscleInline(admin.TabularInline):
    """Rôles des muscles d'un exercice (rôle unique par muscle)."""

    model = ExerciseMuscle
    extra = 0


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    """Bibliothèque d'exercices (globale + personnels)."""

    list_display = ("id", "name", "movement_type", "is_global", "is_archived", "created_at")
    list_filter = ("is_global", "is_archived", "movement_type")
    search_fields = ("name", "description")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [ExerciseMuscleInline]


@admin.register(ExerciseMuscle)
class ExerciseMuscleAdmin(admin.ModelAdmin):
    """Liens exercice/muscle (consultation directe)."""

    list_display = ("id", "exercise", "muscle", "role")
    list_filter = ("role",)
    search_fields = ("exercise__name", "muscle__name")
    readonly_fields = ("id", "created_at", "updated_at")
