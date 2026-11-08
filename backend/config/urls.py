from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from core import views

urlpatterns = [
    # Santé du service (app, base de données, Redis).
    path("api/v1/health/", views.HealthView.as_view(), name="health"),
    # Feature 02 : authentification et profil.
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/users/", include("apps.accounts.user_urls")),
    # Feature 03 : sportifs, coachs, équipes et partage de données.
    path("api/v1/athletes/", include("apps.athletes.urls")),
    path("api/v1/coaches/", include("apps.coaches.urls")),
    path("api/v1/teams/", include("apps.teams.urls")),
    path("api/v1/access-grants/", include("apps.teams.grant_urls")),
    # Feature 04 : capteurs.
    path("api/v1/devices/", include("apps.devices.urls")),
    path("api/v1/device-models/", include("apps.devices.model_urls")),
    # Contrat OpenAPI versionné dans le repo (décision n°14) : `make schema`.
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[AllowAny]),
        name="schema",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
