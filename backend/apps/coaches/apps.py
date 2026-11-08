from django.apps import AppConfig


class CoachesConfig(AppConfig):
    """Feature 03 : profils coach."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.coaches"
    label = "coaches"
    verbose_name = "Coachs"
