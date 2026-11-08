from django.apps import AppConfig


class ExercisesConfig(AppConfig):
    """Feature 05 : bibliothèque d'exercices (groupes et muscles)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.exercises"
    label = "exercises"
    verbose_name = "Exercices"
