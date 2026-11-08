from django.apps import AppConfig


class AuditConfig(AppConfig):
    """Feature 03 : audit minimal des mutations de droits et lectures coach."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
    verbose_name = "Audit"
