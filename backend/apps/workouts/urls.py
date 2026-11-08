"""Routes de la feature 05 : ``/api/v1/workouts/``."""

from django.urls import path

from apps.workouts import views

urlpatterns = [
    path("", views.WorkoutListView.as_view(), name="workouts_list"),
    path("<uuid:pk>/", views.WorkoutDetailView.as_view(), name="workouts_detail"),
    path(
        "<uuid:pk>/exercises/",
        views.WorkoutExercisesReplaceView.as_view(),
        name="workouts_exercises_replace",
    ),
]
