"""Routes de la feature 04 : ``/api/v1/devices/``."""

from django.urls import path

from apps.devices import views

urlpatterns = [
    path("", views.DeviceListView.as_view(), name="devices_list"),
    path("<uuid:pk>/", views.DeviceDetailView.as_view(), name="devices_detail"),
]
