"""Routes de la feature 05 : ``/api/v1/exercises/``."""

from django.urls import path

from apps.exercises import views

urlpatterns = [
    path("", views.ExerciseListView.as_view(), name="exercises_list"),
    path("<uuid:pk>/", views.ExerciseDetailView.as_view(), name="exercises_detail"),
]
