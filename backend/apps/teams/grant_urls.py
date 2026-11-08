"""Routes de la feature 03 : ``/api/v1/access-grants/``."""

from django.urls import path

from apps.teams import views

urlpatterns = [
    path("", views.AccessGrantListView.as_view(), name="access_grants_list"),
    path("<uuid:pk>/accept/", views.AccessGrantAcceptView.as_view(), name="access_grant_accept"),
    path("<uuid:pk>/revoke/", views.AccessGrantRevokeView.as_view(), name="access_grant_revoke"),
]
