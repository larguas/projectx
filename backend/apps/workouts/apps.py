from django.apps import AppConfig


class WorkoutsConfig(AppConfig):
    """Feature 05 : plans d'entraînement (workouts)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workouts"
    label = "workouts"
    verbose_name = "Entraînements"
