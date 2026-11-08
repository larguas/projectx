"""Admin Django de la feature 03 (app ``teams``)."""

from django.contrib import admin

from apps.teams.models import AccessGrant, Team, TeamMembership


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    """Équipes : le propriétaire est visible via l'email."""

    list_display = ("id", "name", "owner_email", "created_at")
    search_fields = ("name", "owner__email")
    readonly_fields = ("id", "owner", "created_at", "updated_at")

    @admin.display(description="Email du propriétaire")
    def owner_email(self, obj) -> str:
        return obj.owner.email


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    """Appartenances : l'email du membre est visible via le lien."""

    list_display = ("id", "team", "user_email", "role", "status", "created_at")
    list_filter = ("role", "status")
    search_fields = ("team__name", "user__email")
    readonly_fields = ("id", "team", "user", "created_at", "updated_at")

    @admin.display(description="Email du membre")
    def user_email(self, obj) -> str:
        return obj.user.email


@admin.register(AccessGrant)
class AccessGrantAdmin(admin.ModelAdmin):
    """Autorisations de partage : en lecture seule (l'audit trace les mutations)."""

    list_display = (
        "id",
        "athlete_user_email",
        "grantee_type",
        "scopes",
        "status",
        "granted_at",
        "revoked_at",
        "expires_at",
    )
    list_filter = ("status", "grantee_type")
    search_fields = ("athlete__user__email",)
    readonly_fields = (
        "id",
        "athlete",
        "granted_by",
        "grantee_type",
        "grantee_coach",
        "grantee_team",
        "scopes",
        "status",
        "granted_at",
        "revoked_at",
        "expires_at",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Email du sportif")
    def athlete_user_email(self, obj) -> str:
        return obj.athlete.user.email
