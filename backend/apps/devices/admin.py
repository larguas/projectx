"""Admin Django de la feature 04 (app ``devices``).

Le catalogue des modèles est géré ici (les utilisateurs n'ont qu'une lecture
API, cf. ``GET /api/v1/device-models/``) ; les capteurs sont aussi listés pour
l'exploitation — le retrait d'un capteur passe par ``status = retired``, jamais
par une suppression de ligne.
"""

from django.contrib import admin

from apps.devices.models import Device, DeviceModel


@admin.register(DeviceModel)
class DeviceModelAdmin(admin.ModelAdmin):
    """Catalogue des modèles de capteurs."""

    list_display = (
        "id",
        "manufacturer",
        "name",
        "protocol_version",
        "connection_types",
        "created_at",
    )
    list_filter = ("manufacturer", "protocol_version")
    search_fields = ("manufacturer", "name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    """Capteurs : la désactivation logique passe par ``status``."""

    list_display = ("id", "serial_number", "device_model", "owner_email", "status", "last_seen_at")
    list_filter = ("status", "device_model")
    search_fields = ("serial_number", "name", "owner__email")
    readonly_fields = ("id", "created_at", "updated_at")

    @admin.display(description="Email du propriétaire")
    def owner_email(self, obj) -> str:
        return obj.owner.email
