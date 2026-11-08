"""Vues de la feature 04 (app ``devices``).

- ``GET/POST /api/v1/devices/`` : liste des capteurs visibles (sélecteur
  ``apps.devices.selectors.visible_devices``) + création d'un capteur pour
  l'utilisateur connecté ;
- ``GET/PATCH/DELETE /api/v1/devices/{id}/`` : détail visible selon
  ``selectors.can_read_device`` (404 sinon — l'existence n'est pas révélée),
  mise à jour et désactivation logique réservées au propriétaire. Le DELETE ne
  supprime jamais la ligne (``status -> retired``) ; PUT est refusé (405), le
  périmètre API est GET/PATCH/DELETE ;
- ``GET /api/v1/device-models/`` : catalogue des modèles, lecture seule pour
  tout utilisateur authentifié.

Audit (même principe que la feature 03) : toute lecture par un non-propriétaire
émet un événement (``device.viewed`` / ``device.listed``) via
``apps.audit.services.record_event`` ; la désactivation logique est aussi
auditée (``device.retired``, « suppression » sensible). La metadata ne contient
que des compteurs, aucune donnée personnelle.
"""

from rest_framework import exceptions, generics, permissions, status
from rest_framework.response import Response

from apps.audit.services import record_event
from apps.devices import selectors, serializers, services
from core.exceptions import error_response

_ERROR_STATUS = {
    "forbidden": status.HTTP_403_FORBIDDEN,
    "conflict": status.HTTP_409_CONFLICT,
}


def _service_error(exc: services.DevicesServiceError) -> Response:
    return error_response(_ERROR_STATUS[exc.code], code=exc.code, message=exc.message)


def _profile_of(user):
    """Profil sportif de ``user`` ou ``None`` (utilisé pour l'audit)."""
    from apps.athletes.models import AthleteProfile

    return AthleteProfile.objects.filter(user=user).first()


class DeviceListView(generics.ListCreateAPIView):
    """Liste des capteurs visibles + création d'un capteur."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.DeviceSerializer
    filterset_fields = ("status", "device_model")

    def get_queryset(self):
        return selectors.visible_devices(self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        granted_count = queryset.exclude(owner=request.user).count()
        if granted_count:
            record_event(
                request.user,
                "device.listed",
                None,
                metadata={"granted_devices": granted_count},
                request=request,
            )
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = serializers.CreateDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            device = services.create_device(request.user, serializer.validated_data)
        except services.DevicesServiceError as exc:
            return _service_error(exc)
        output = serializers.DeviceSerializer(device, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class DeviceDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Détail d'un capteur visible + mise à jour / retrait par le propriétaire."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.DeviceSerializer
    http_method_names = ["get", "patch", "delete"]  # pas de PUT : périmètre API

    def get_object(self):
        from apps.devices.models import Device

        device = Device.objects.filter(pk=self.kwargs["pk"]).first()
        if device is None or not selectors.can_read_device(self.request.user, device):
            raise exceptions.NotFound("Capteur introuvable.")
        return device

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.owner_id != request.user.pk:
            record_event(
                request.user,
                "device.viewed",
                instance,
                athlete=_profile_of(instance.owner),
                request=request,
            )
        return super().retrieve(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            device = services.update_device(request.user, instance, serializer.validated_data)
        except services.DevicesServiceError as exc:
            return _service_error(exc)
        output = serializers.DeviceSerializer(device, context={"request": request})
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            device = services.retire_device(request.user, instance)
        except services.DevicesServiceError as exc:
            return _service_error(exc)
        record_event(
            request.user,
            "device.retired",
            device,
            athlete=_profile_of(device.owner),
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceModelListView(generics.ListAPIView):
    """Catalogue des modèles de capteurs (lecture seule)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.DeviceModelSerializer
    filterset_fields = ("manufacturer",)

    def get_queryset(self):
        from apps.devices.models import DeviceModel

        return DeviceModel.objects.all()
