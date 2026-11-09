"""Routes de la feature 03 : ``/api/v1/athletes/``.

Les routes imbriquées ``setups/current/`` et ``calibrations/`` (feature 05b)
pointent vers les vues de l'app ``setups`` — qui possède la ressource ;
``sessions/suggested-setup/`` (feature 06) pointe vers l'app ``sessions``.
"""

from django.urls import path

from apps.athletes import views
from apps.sessions import views as sessions_views
from apps.setups import views as setups_views

urlpatterns = [
    path("", views.AthleteListView.as_view(), name="athletes_list"),
    path("<uuid:pk>/", views.AthleteDetailView.as_view(), name="athletes_detail"),
    path(
        "<uuid:athlete_pk>/setups/current/",
        setups_views.AthleteCurrentSetupsView.as_view(),
        name="athletes_setups_current",
    ),
    path(
        "<uuid:athlete_pk>/calibrations/",
        setups_views.AthleteCalibrationsView.as_view(),
        name="athletes_calibrations_list",
    ),
    path(
        "<uuid:athlete_pk>/sessions/suggested-setup/",
        sessions_views.AthleteSuggestedSetupView.as_view(),
        name="athletes_sessions_suggested_setup",
    ),
]
