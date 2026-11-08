from django.apps import AppConfig


class DevicesConfig(AppConfig):
    """Feature 04 : capteurs."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.devices"
    label = "devices"
    verbose_name = "Capteurs"
