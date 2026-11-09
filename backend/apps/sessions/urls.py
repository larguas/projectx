"""Routes de la feature 06 : ``/api/v1/sessions/``.

La route imbriquée ``/athletes/{id}/sessions/suggested-setup/`` vit dans les
urls de l'app hôte ``athletes`` (même vue, app ``sessions``) — même convention
que les routes imbriquées 05b.
"""

from django.urls import path

from apps.sessions import views

urlpatterns = [
    path("", views.SessionListView.as_view(), name="sessions_list"),
    path("<uuid:pk>/", views.SessionDetailView.as_view(), name="sessions_detail"),
    path("<uuid:pk>/start/", views.SessionStartView.as_view(), name="sessions_start"),
    path("<uuid:pk>/complete/", views.SessionCompleteView.as_view(), name="sessions_complete"),
    path("<uuid:pk>/cancel/", views.SessionCancelView.as_view(), name="sessions_cancel"),
    path(
        "<uuid:pk>/channels/",
        views.SessionChannelListUpdateView.as_view(),
        name="sessions_channels",
    ),
    path(
        "<uuid:pk>/devices/",
        views.SessionDeviceListUpdateView.as_view(),
        name="sessions_devices",
    ),
    path(
        "<uuid:pk>/annotations/",
        views.SessionAnnotationListView.as_view(),
        name="sessions_annotations_list",
    ),
    path(
        "<uuid:pk>/annotations/<uuid:aid>/",
        views.SessionAnnotationDetailView.as_view(),
        name="sessions_annotations_detail",
    ),
]
