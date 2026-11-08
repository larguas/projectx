"""Routes profil de la feature 02 : ``/api/v1/users/``."""

from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("me/", views.MeView.as_view(), name="users_me"),
]
