from django.apps import AppConfig


class AthletesConfig(AppConfig):
    """Feature 03 : profils sportifs."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.athletes"
    label = "athletes"
    verbose_name = "Sportifs"
