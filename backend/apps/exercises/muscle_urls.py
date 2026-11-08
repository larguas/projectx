"""Routes de la feature 05 : ``/api/v1/muscles/`` (catalogue, lecture seule).

Le guide de placement imbriqué (feature 05b) pointe vers la vue de l'app
``setups`` — qui possède la ressource.
"""

from django.urls import path

from apps.exercises import views
from apps.setups import views as setups_views

urlpatterns = [
    path("", views.MuscleListView.as_view(), name="muscles_list"),
    path(
        "<uuid:muscle_pk>/placement-guide/",
        setups_views.PlacementGuideView.as_view(),
        name="muscles_placement_guide",
    ),
]
