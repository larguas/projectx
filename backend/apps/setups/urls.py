"""Routes de la feature 05b : ``/api/v1/setups/`` (dont ``compare/``).

Ordre significatif : ``compare/`` avant le détail ``<uuid:pk>/``.
"""

from django.urls import path

from apps.setups import views

urlpatterns = [
    path("", views.SetupListView.as_view(), name="setups_list"),
    path("compare/", views.SetupCompareView.as_view(), name="setups_compare"),
    path("<uuid:pk>/", views.SetupDetailView.as_view(), name="setups_detail"),
    path(
        "<uuid:pk>/new-version/",
        views.SetupNewVersionView.as_view(),
        name="setups_new_version",
    ),
    path("<uuid:pk>/channels/", views.SetupChannelsView.as_view(), name="setups_channels"),
]
