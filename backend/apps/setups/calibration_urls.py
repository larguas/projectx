"""Routes de la feature 05b : ``/api/v1/calibrations/``."""

from django.urls import path

from apps.setups import views

urlpatterns = [
    path(
        "<uuid:pk>/invalidate/",
        views.CalibrationInvalidateView.as_view(),
        name="calibrations_invalidate",
    ),
]
