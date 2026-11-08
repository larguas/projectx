"""Routes de la feature 03 : ``/api/v1/athletes/``."""

from django.urls import path

from apps.athletes import views

urlpatterns = [
    path("", views.AthleteListView.as_view(), name="athletes_list"),
    path("<uuid:pk>/", views.AthleteDetailView.as_view(), name="athletes_detail"),
]
