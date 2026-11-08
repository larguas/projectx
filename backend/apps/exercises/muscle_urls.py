"""Routes de la feature 05 : ``/api/v1/muscles/`` (catalogue, lecture seule)."""

from django.urls import path

from apps.exercises import views

urlpatterns = [
    path("", views.MuscleListView.as_view(), name="muscles_list"),
]
