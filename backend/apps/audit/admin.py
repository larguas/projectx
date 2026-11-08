"""Admin Django de la feature 03 (app ``audit``) : consultation seule.

L'insertion se fait via ``audit.services.record_event`` ; l'admin ne permet
que de consulter (pas d'ajout manuel, pas de modification, pas de suppression).
"""

from django.contrib import admin

from apps.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """Événements d'audit immuables : lecture seule."""

    list_display = ("id", "action", "actor_email", "target_type", "athlete", "created_at")
    list_filter = ("action",)
    search_fields = ("action", "actor__email", "target_type")
    readonly_fields = (
        "id",
        "actor",
        "action",
        "target_type",
        "target_id",
        "athlete",
        "ip",
        "user_agent",
        "metadata",
        "created_at",
    )

    @admin.display(description="Email de l'acteur")
    def actor_email(self, obj) -> str:
        return obj.actor.email

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
