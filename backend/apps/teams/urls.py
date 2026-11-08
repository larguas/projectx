"""Routes de la feature 03 : ``/api/v1/teams/``."""

from django.urls import path

from apps.teams import views

urlpatterns = [
    path("", views.TeamListView.as_view(), name="teams_list"),
    path("<uuid:pk>/", views.TeamDetailView.as_view(), name="teams_detail"),
    path("<uuid:team_id>/members/", views.MemberListView.as_view(), name="teams_members"),
    path(
        "<uuid:team_id>/members/<uuid:user_id>/",
        views.MemberDetailView.as_view(),
        name="teams_member",
    ),
]
