"""Admin Django de la feature 02 : ``User`` et ``DeviceAuthorization``."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import DeviceAuthorization, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin adapté à l'utilisateur personnalisé (email comme identifiant)."""

    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Informations personnelles", {"fields": ("first_name", "last_name")}),
        (
            "Permissions et dates",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                    "last_login",
                    "date_joined",
                )
            },
        ),
        ("EMG", {"fields": ("email_verified_at", "locale", "timezone")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)


@admin.register(DeviceAuthorization)
class DeviceAuthorizationAdmin(admin.ModelAdmin):
    """Autorisations de clients : en lecture seule (codes stockés hachés)."""

    list_display = (
        "id",
        "client_type",
        "client_name",
        "status",
        "user",
        "created_at",
        "expires_at",
    )
    list_filter = ("status", "client_type")
    search_fields = ("client_name", "client_version")
    readonly_fields = (
        "id",
        "device_code_hash",
        "user_code_hash",
        "status",
        "user",
        "client_type",
        "client_name",
        "client_version",
        "expires_at",
        "last_polled_at",
        "poll_attempts",
        "created_at",
        "updated_at",
    )
