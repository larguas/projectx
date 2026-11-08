"""Routes de la feature 03 : ``/api/v1/coaches/``."""

from django.urls import path

from apps.coaches import views

urlpatterns = [
    path("", views.CoachListView.as_view(), name="coaches_list"),
    path("<uuid:pk>/", views.CoachDetailView.as_view(), name="coaches_detail"),
]
