"""Sérialiseurs de la feature 04 (app ``devices``).

L'email du propriétaire n'est exposé qu'à ce dernier : un coach qui voit les
capteurs d'un sportif via un grant actif ne reçoit pas son adresse email
(donnée personnelle, cf. règle « données privées par défaut »).

Sur un capteur, seuls ``name``, ``firmware_version`` et
``calibration_defaults`` sont modifiables (PATCH, par le propriétaire) :
- ``device_model`` / ``serial_number`` forment l'identité du matériel ;
- ``status`` gère la désactivation logique (DELETE) et n'est pas réactivable
  via l'API (réactivation éventuelle en admin).
"""

from rest_framework import serializers

from apps.devices.models import Device, DeviceModel


class DeviceModelSerializer(serializers.ModelSerializer):
    """Entrée du catalogue des modèles (lecture seule pour les utilisateurs)."""

    class Meta:
        model = DeviceModel
        fields = (
            "id",
            "manufacturer",
            "name",
            "protocol_version",
            "connection_types",
            "capabilities",
        )
        read_only_fields = fields


class DeviceSerializer(serializers.ModelSerializer):
    """Capteur ; ``owner_email`` est uniquement renseigné pour le propriétaire."""

    owner_email = serializers.SerializerMethodField()
    device_model = DeviceModelSerializer(read_only=True)

    class Meta:
        model = Device
        fields = (
            "id",
            "owner_email",
            "device_model",
            "serial_number",
            "name",
            "firmware_version",
            "status",
            "last_seen_at",
            "calibration_defaults",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner_email",
            "device_model",
            "serial_number",
            "status",
            "last_seen_at",
            "created_at",
            "updated_at",
        )

    def get_owner_email(self, obj) -> str | None:
        request = self.context.get("request")
        if request is not None and getattr(request.user, "pk", None) == obj.owner_id:
            return obj.owner.email
        return None


class CreateDeviceSerializer(serializers.Serializer):
    """Création d'un capteur pour l'utilisateur connecté."""

    device_model = serializers.PrimaryKeyRelatedField(queryset=DeviceModel.objects.all())
    serial_number = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    firmware_version = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default=""
    )
    calibration_defaults = serializers.JSONField(required=False, default=dict)
