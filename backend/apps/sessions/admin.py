"""Admin Django de la feature 06 (app ``sessions``).

Les séances sont listées pour l'exploitation ; les appareils, canaux et
annotations se consultent en inline EN LECTURE SEULE : le chemin opérationnel
est l'API (création avec copie des canaux du setup, remplacement atomique via
``apps.sessions.services.replace_channels`` / ``replace_devices``, annotations
via leurs endpoints dédiés) — éditer ces lignes à la main contournerait les
contrôles d'accessibilité et de capacités. Le statut et ses horodatages sont
EN LECTURE SEULE : la machine à états ne passe que par les services
(``start_session`` / ``complete_session`` / ``cancel_session`` — jamais de
``save()`` direct). L'identité des utilisateurs n'est exposée que sous forme
d'email (convention admin).
"""

from django.contrib import admin

from apps.sessions.models import Session, SessionAnnotation, SessionChannel, SessionDevice


class SessionDeviceInline(admin.TabularInline):
    """Appareils d'une séance (rôle + décalage d'horloge estimé en feature 07)."""

    model = SessionDevice
    extra = 0
    readonly_fields = ("id", "session", "device", "role", "clock_offset_ms")


class SessionChannelInline(admin.TabularInline):
    """Canaux d'une séance (figés depuis le setup ou déclarés à la main)."""

    model = SessionChannel
    extra = 0
    readonly_fields = (
        "id",
        "session",
        "device",
        "channel_id",
        "muscle",
        "side",
        "data_type",
        "units",
        "calibration",
        "setup_channel",
    )


class SessionAnnotationInline(admin.TabularInline):
    """Annotations / marqueurs d'une séance (tri par ``offset_ms``)."""

    model = SessionAnnotation
    extra = 0
    readonly_fields = ("id", "session", "kind", "offset_ms", "text", "metadata", "author")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    """Séances d'acquisition (machine à états, placement figé)."""

    list_display = (
        "id",
        "athlete",
        "session_type",
        "status",
        "setup",
        "setup_declared",
        "source",
        "started_at",
        "created_at",
    )
    list_filter = ("session_type", "status", "source")
    search_fields = ("athlete__user__email", "notes", "setup__name")
    readonly_fields = (
        "id",
        "status",
        "started_at",
        "ended_at",
        "setup_declared",
        "created_by",
        "created_at",
        "updated_at",
    )
    inlines = [SessionDeviceInline, SessionChannelInline, SessionAnnotationInline]


@admin.register(SessionDevice)
class SessionDeviceAdmin(admin.ModelAdmin):
    """Appareils de séance (consultation directe)."""

    list_display = ("id", "session", "device", "role", "clock_offset_ms")
    list_filter = ("role",)
    search_fields = ("device__name", "session__athlete__user__email")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SessionChannel)
class SessionChannelAdmin(admin.ModelAdmin):
    """Canaux de séance (consultation directe)."""

    list_display = ("id", "session", "device", "channel_id", "muscle", "side", "data_type")
    list_filter = ("side", "data_type")
    search_fields = ("muscle__name", "device__name", "session__athlete__user__email")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SessionAnnotation)
class SessionAnnotationAdmin(admin.ModelAdmin):
    """Annotations / marqueurs de séance (consultation directe)."""

    list_display = ("id", "session", "kind", "offset_ms", "author", "created_at")
    list_filter = ("kind",)
    search_fields = ("text", "session__athlete__user__email")
    readonly_fields = ("id", "author", "created_at")
