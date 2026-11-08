"""Routes de la feature 04 : ``/api/v1/device-models/`` (catalogue, lecture seule)."""

from django.urls import path

from apps.devices import views

urlpatterns = [
    path("", views.DeviceModelListView.as_view(), name="device_models_list"),
]
