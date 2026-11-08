"""Sérialiseurs de la feature 05b (app ``setups``).

Règles d'exposition :
- l'identité du créateur n'est JAMAIS exposée sur un setup (ni email ni pk de
  ``created_by``) : l'accès à un setup est l'accès au sportif rattaché ;
- ``athlete`` est une référence compacte (``id`` + ``sport``) : pas d'email,
  même pour le propriétaire (convention « données privées par défaut ») ;
- les canaux exposent muscle et capteur en références compactes ; la photo est
  servie via ``default_storage`` (URL relative), jamais de bytes bruts ;
- ``editable`` est calculé pour l'utilisateur courant (propriétaire du profil,
  ou grant ``setups:write`` actif sur le sportif rattaché).

Écriture : ``CreateSetupSerializer`` / ``UpdateSetupSerializer`` /
``NewVersionSerializer`` / ``SetChannelsSerializer`` (liste COMPLÈTE des canaux,
champs détaillés optionnels — mode simple) / ``InvalidateCalibrationSerializer``.
L'accès est contrôlé en service par ``core.access`` (scopes ``setups:read`` /
``setups:write``, déjà enregistrés en feature 03).
"""

from rest_framework import serializers

from apps.athletes.models import AthleteProfile
from apps.devices.models import Device, DeviceModel
from apps.exercises.models import Muscle
from apps.setups.models import Calibration, PlacementGuide, SensorSetup, SetupChannel


class AthleteReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un profil sportif (``id`` + ``sport``).

    ``ref_name`` distinct de celui de l'app ``workouts`` (même projection) :
    drf-spectacular exige un nom de composant unique par schéma.
    """

    class Meta:
        model = AthleteProfile
        fields = ("id", "sport")
        read_only_fields = fields
        ref_name = "SetupsAthleteReference"


class MuscleReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un muscle du catalogue (``id``, ``code``, ``name``)."""

    class Meta:
        model = Muscle
        fields = ("id", "code", "name")
        read_only_fields = fields


class DeviceModelReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un modèle de capteur (``id``, fabriquant, nom)."""

    class Meta:
        model = DeviceModel
        fields = ("id", "manufacturer", "name")
        read_only_fields = fields


class DeviceReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un capteur (``id``, nom, modèle)."""

    device_model = DeviceModelReferenceSerializer(read_only=True)

    class Meta:
        model = Device
        fields = ("id", "name", "device_model")
        read_only_fields = fields


class SetupReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'une version de setup (``id``, ``name``, ``version``)."""

    class Meta:
        model = SensorSetup
        fields = ("id", "name", "version")
        read_only_fields = fields


class SetupChannelReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un canal dans une calibration (muscle + côté)."""

    muscle = MuscleReferenceSerializer(read_only=True)

    class Meta:
        model = SetupChannel
        fields = ("id", "channel_id", "side", "muscle")
        read_only_fields = fields


class SetupChannelSerializer(serializers.ModelSerializer):
    """Canal d'un setup (lecture) : muscle et capteur en références compactes.

    La photo est servie en URL relative via ``default_storage`` (jamais de
    bytes bruts dans la réponse).
    """

    device = DeviceReferenceSerializer(read_only=True)
    muscle = MuscleReferenceSerializer(read_only=True)
    photo = serializers.FileField(read_only=True, use_url=False)

    class Meta:
        model = SetupChannel
        fields = (
            "id",
            "device",
            "channel_id",
            "muscle",
            "side",
            "position_note",
            "inter_electrode_distance_mm",
            "skin_prep_done",
            "photo",
        )
        read_only_fields = fields


class SensorSetupSerializer(serializers.ModelSerializer):
    """Setup de placement (lecture) ; ``editable`` est calculé pour le courant.

    ``created_by`` n'est JAMAIS exposé (donnée d'audit — l'accès au setup est
    l'accès au sportif rattaché). ``is_used`` expose l'état figé (point
    d'extension unique de la feature 06) sans exposer le marqueur interne
    ``used_at``.
    """

    athlete = AthleteReferenceSerializer(read_only=True)
    parent = serializers.PrimaryKeyRelatedField(read_only=True)
    channels = SetupChannelSerializer(many=True, read_only=True)
    is_used = serializers.BooleanField(read_only=True)
    editable = serializers.SerializerMethodField()

    class Meta:
        model = SensorSetup
        fields = (
            "id",
            "athlete",
            "name",
            "version",
            "parent",
            "placement_inherited_from_parent",
            "detail_level",
            "is_current",
            "is_used",
            "notes",
            "channels",
            "editable",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_editable(self, obj) -> bool:
        from apps.setups import selectors

        request = self.context.get("request")
        user = getattr(request, "user", None) if request is not None else None
        return selectors.can_write_setup(user, obj)


class CreateSetupSerializer(serializers.Serializer):
    """Création d'un setup (``POST /api/v1/setups/``).

    ``athlete`` est requis : un setup n'existe que pour un sportif (pas de
    « orphelin »). L'attachement est contrôlé en service par ``core.access``
    avec le scope ``setups:write`` — on ne peut pas « injecter » un setup dans
    la vue d'un coach tiers. Le nom doit être libre pour ce sportif
    (``name_taken``, 409 sinon) : l'identité d'un setup est ``(athlete, name,
    version)``.
    """

    name = serializers.CharField(max_length=200)
    athlete = serializers.PrimaryKeyRelatedField(queryset=AthleteProfile.objects.all())
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class UpdateSetupSerializer(serializers.Serializer):
    """Mise à jour partielle d'un setup non utilisé (``PATCH /api/v1/setups/{id}/``).

    Tous les champs sont optionnels. Le rattachement au sportif ne change PAS
    ici (changer l'athlète créerait un autre setup — à créer explicitement) ;
    les canaux ne se modifient PAS ici non plus : seul
    ``PUT /api/v1/setups/{id}/channels/`` remplace la liste. Refusé si le
    setup est utilisé (``setup_frozen``, 409).
    """

    name = serializers.CharField(max_length=200, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class NewVersionSerializer(serializers.Serializer):
    """Nouvelle version d'un setup (``POST /api/v1/setups/{id}/new-version/``).

    ``placement_unchanged`` (défaut ``False``) : ``True`` quand seul un détail
    non physique change (nom, notes) — les calibrations de la version
    précédente sont alors rattachées à la nouvelle version. Sinon elles restent
    liées à l'ancienne (une MVC n'a de sens que pour un placement donné).
    """

    placement_unchanged = serializers.BooleanField(required=False, default=False)


class SetupChannelInputSerializer(serializers.Serializer):
    """Une entrée du remplacement des canaux d'un setup.

    Tous les champs détaillés (``position_note``, ``inter_electrode_distance_mm``,
    ``skin_prep_done``, ``photo``) sont optionnels : un canal sans aucun champ
    détaillé est un canal « simple » (muscle + côté) — le niveau de détail du
    setup est recalculé en service après le remplacement.

    ``device`` est optionnel (canal déclaré sans capteur précis — placement
    générique) ; ``muscle`` référence TOUJOURS ``exercises.Muscle`` (jamais
    ``MuscleGroup``, décision feature 05).
    """

    device = serializers.PrimaryKeyRelatedField(
        queryset=Device.objects.all(), required=False, allow_null=True, default=None
    )
    channel_id = serializers.IntegerField(min_value=1)
    muscle = serializers.PrimaryKeyRelatedField(queryset=Muscle.objects.all())
    side = serializers.ChoiceField(choices=SetupChannel.Side.choices, required=False, default="na")
    position_note = serializers.CharField(required=False, allow_blank=True, default="")
    inter_electrode_distance_mm = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, default=None
    )
    skin_prep_done = serializers.BooleanField(required=False, allow_null=True, default=None)
    photo = serializers.FileField(required=False, allow_null=True, default=None)


def _validate_channel_entries(value: list) -> list:
    """Un même canal de capteur ne peut pas apparaître deux fois dans un setup."""
    seen: set = set()
    for entry in value:
        key = (entry["device"].pk if entry["device"] is not None else None, entry["channel_id"])
        if key in seen:
            raise serializers.ValidationError(
                "Un même canal de capteur ne peut apparaître qu'une fois dans le setup."
            )
        seen.add(key)
    return value


class SetChannelsSerializer(serializers.Serializer):
    """Remplacement de la liste des canaux d'un setup (``PUT .../channels/``).

    ``channels`` est la liste COMPLÈTE : les canaux existants sont supprimés et
    les nouveaux créés atomiquement en service. Une liste vide est autorisée
    (setup sans canal déclaré). Les doublons ``(device, channel_id)`` sont
    refusés ici ; le niveau de détail effectif est recalculé ensuite en service
    (forcé à ``simple`` si aucun champ détaillé n'est renseigné).
    """

    channels = SetupChannelInputSerializer(many=True, required=False, default=list)

    def validate_channels(self, value: list) -> list:
        return _validate_channel_entries(value)


class CalibrationSerializer(serializers.ModelSerializer):
    """Calibration (lecture) ; ``applicable`` est calculé pour le moment courant.

    Rattachée à une version PRÉCISE d'un setup : les références ``setup`` et
    ``setup_channel`` sont compactes (le lecteur a déjà accès au setup lui-même
    — même règle d'accès, scope ``setups:read`` sur le profil rattaché).
    """

    athlete = AthleteReferenceSerializer(read_only=True)
    setup = SetupReferenceSerializer(read_only=True)
    setup_channel = SetupChannelReferenceSerializer(read_only=True)
    applicable = serializers.SerializerMethodField()

    class Meta:
        model = Calibration
        fields = (
            "id",
            "athlete",
            "setup",
            "setup_channel",
            "type",
            "values",
            "algorithm_version",
            "valid_from",
            "valid_until",
            "invalidated_at",
            "invalidation_reason",
            "applicable",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_applicable(self, obj) -> bool:
        return obj.is_applicable


class InvalidateCalibrationSerializer(serializers.Serializer):
    """Invalidation d'une calibration (``POST /calibrations/{id}/invalidate/``).

    ``reason`` est optionnel mais recommandé ; l'invalidation est irréversible
    côté API (pas de réactivation : on crée une nouvelle calibration).
    """

    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class PlacementGuideSerializer(serializers.ModelSerializer):
    """Guide de placement d'un muscle (lecture) ; l'image est servie en URL
    relative via ``default_storage`` (jamais de bytes bruts)."""

    muscle = MuscleReferenceSerializer(read_only=True)
    image = serializers.FileField(read_only=True, use_url=False)

    class Meta:
        model = PlacementGuide
        fields = ("id", "muscle", "title", "instructions", "reference", "image")
        read_only_fields = fields


class SetupComparisonSerializer(serializers.Serializer):
    """Comparabilité de deux setups (réponse de ``GET /setups/compare/``).

    ``level`` est l'un de ``identical`` / ``equivalent`` / ``approximate`` /
    ``different`` / ``unknown`` ; ``reasons`` sont des chaînes stables et
    lisibles, réutilisables telles quelles par l'IA (cf.
    ``services.compare_setups``).
    """

    level = serializers.ChoiceField(
        choices=["identical", "equivalent", "approximate", "different", "unknown"]
    )
    reasons = serializers.ListField(child=serializers.CharField())


class CompareSetupsQuerySerializer(serializers.Serializer):
    """Paramètres de requête de ``GET /setups/compare/?a={id}&b={id}``."""

    a = serializers.UUIDField()
    b = serializers.UUIDField()


class AthleteCalibrationsQuerySerializer(serializers.Serializer):
    """Filtres optionnels de ``GET /athletes/{id}/calibrations/``.

    - ``setup`` : uuid d'une version précise du setup ;
    - ``type`` : ``mvc`` ou ``rest_baseline`` ;
    - ``applicable`` : ``true``/``false`` — non invalidée et non expirée (la
      condition « rattachée au setup de la séance » relève du service
      ``applicable_calibrations``, pas d'un filtre de liste).
    """

    setup = serializers.UUIDField(required=False)
    type = serializers.ChoiceField(choices=Calibration.Type.choices, required=False)
    applicable = serializers.BooleanField(required=False)
