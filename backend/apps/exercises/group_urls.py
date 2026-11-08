"""Routes de la feature 05 : ``/api/v1/muscle-groups/`` (catalogue, lecture seule)."""

from django.urls import path

from apps.exercises import views

urlpatterns = [
    path("", views.MuscleGroupListView.as_view(), name="muscle_groups_list"),
]
