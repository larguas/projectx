from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from core import views

urlpatterns = [
    # Santé du service (app, base de données, Redis).
    path("api/v1/health/", views.HealthView.as_view(), name="health"),
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
