"""Admin Django de la feature 05b (app ``setups``).

Les setups sont listés pour l'exploitation ; les canaux se gèrent en inline
(le chemin opérationnel est l'API — remplacement atomique via
``apps.setups.services.set_channels``). La lignée de versionnage (``version``,
``parent``, ``placement_inherited_from_parent``, ``is_current``, ``used_at``,
``created_by``) est EN LECTURE SEULE : ces champs ne sont modifiés que par les
services (création de version, basculement par mise à jour en base ciblée —
jamais de ``save()`` sur un setup figé) ; les éditer à la main casserait la
lignée. L'identité des utilisateurs n'est exposée que sous forme d'email
(convention admin).
"""

from django.contrib import admin

from apps.setups.models import Calibration, PlacementGuide, SensorSetup, SetupChannel


class SetupChannelInline(admin.TabularInline):
    """Canaux d'un setup (muscle + côté ; champs détaillés optionnels)."""

    model = SetupChannel
    extra = 0


@admin.register(SensorSetup)
class SensorSetupAdmin(admin.ModelAdmin):
    """Setups de placement versionnés (lignée ``parent``, une ``is_current`` par nom)."""

    list_display = (
        "id",
        "name",
        "version",
        "athlete",
        "detail_level",
        "is_current",
        "used_at",
        "created_at",
    )
    list_filter = ("detail_level", "is_current")
    search_fields = ("name", "athlete__user__email")
    readonly_fields = (
        "id",
        "version",
        "parent",
        "placement_inherited_from_parent",
        "used_at",
        "created_by",
        "created_at",
        "updated_at",
    )
    inlines = [SetupChannelInline]


@admin.register(SetupChannel)
class SetupChannelAdmin(admin.ModelAdmin):
    """Canaux de setup (consultation directe)."""

    list_display = ("id", "setup", "device", "channel_id", "muscle", "side")
    list_filter = ("side",)
    search_fields = ("setup__name", "muscle__code", "muscle__name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(PlacementGuide)
class PlacementGuideAdmin(admin.ModelAdmin):
    """Guides de placement par muscle (seedés par migration, gérés ici)."""

    list_display = ("id", "muscle", "title", "reference", "created_at")
    search_fields = ("muscle__code", "muscle__name", "title")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Calibration)
class CalibrationAdmin(admin.ModelAdmin):
    """Calibrations (MVC / baseline de repos), rattachées à une version précise."""

    list_display = (
        "id",
        "athlete",
        "type",
        "setup",
        "valid_from",
        "valid_until",
        "invalidated_at",
        "created_at",
    )
    list_filter = ("type", "invalidated_at")
    search_fields = ("athlete__user__email", "setup__name")
    readonly_fields = ("id", "created_at", "updated_at")
