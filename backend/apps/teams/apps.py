from django.apps import AppConfig


class TeamsConfig(AppConfig):
    """Feature 03 : équipes, membres et autorisations de partage (AccessGrant)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.teams"
    label = "teams"
    verbose_name = "Équipes"
