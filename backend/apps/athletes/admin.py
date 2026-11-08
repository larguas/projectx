"""Admin Django de la feature 03 (app ``athletes``)."""

from django.contrib import admin

from apps.athletes.models import AthleteProfile


@admin.register(AthleteProfile)
class AthleteProfileAdmin(admin.ModelAdmin):
    """Profils sportifs : l'email du propriétaire est visible via le lien."""

    list_display = ("id", "user_email", "sport", "sex", "date_of_birth", "created_at")
    list_filter = ("sex", "sport")
    search_fields = ("user__email", "sport")
    readonly_fields = ("id", "user", "created_at", "updated_at")

    @admin.display(description="Email du propriétaire")
    def user_email(self, obj) -> str:
        return obj.user.email
