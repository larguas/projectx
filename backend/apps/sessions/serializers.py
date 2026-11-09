"""Sérialiseurs de la feature 06 (app ``sessions``).

Exposition : l'identité du créateur n'est JAMAIS exposée sur une séance ;
``athlete``, ``setup``, ``exercise``, ``workout``, appareils et muscles sont
des références compactes. ``warnings`` est calculé dans le détail
(``setup_not_declared`` si la séance a été créée sans setup — même
avertissement que la réponse de création) et ``editable`` est calculé pour
l'utilisateur courant (grant ``sessions:write`` sur le sportif rattaché).

Écriture : ``SessionCreateSerializer`` (validation croisée
``calibration`` ↔ ``setup`` / ``calibration_type``), ``SessionUpdateSerializer``
(``notes`` / ``acquisition_config`` — jamais le statut),
``ReplaceChannelsSerializer`` / ``ReplaceDevicesSerializer`` (remplacement
intégral pendant ``created``) et ``AnnotationSerializer``.
"""

from rest_framework import serializers
from rest_framework.fields import empty

from apps.athletes.models import AthleteProfile
from apps.devices.models import Device, DeviceModel
from apps.exercises.models import Exercise, Muscle
from apps.sessions.models import Session, SessionAnnotation, SessionChannel, SessionDevice
from apps.setups.models import Calibration, SensorSetup
from apps.workouts.models import Workout


class OptionalBooleanQueryField(serializers.BooleanField):
    """Booléen de paramètre de requête à trois états (absent / ``true`` / ``false``).

    DRF traite le ``QueryDict`` comme un formulaire : un champ booléen MANQUANT
    y vaudrait ``False``. Pour un filtre optionnel, l'absence doit rester
    ABSENTE (pas de filtre) — d'où ce surclassement (même pattern que
    ``apps.setups.serializers.OptionalBooleanQueryField``).
    """

    default_empty_html = empty


class SessionsAthleteReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un profil sportif (``id`` + ``sport``)."""

    class Meta:
        model = AthleteProfile
        fields = ("id", "sport")
        read_only_fields = fields


class SessionsSetupReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'une version de setup (``id``, ``name``, ``version``)."""

    class Meta:
        model = SensorSetup
        fields = ("id", "name", "version")
        read_only_fields = fields


class SessionsExerciseReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un exercice (``id``, ``name``, ``movement_type``)."""

    class Meta:
        model = Exercise
        fields = ("id", "name", "movement_type")
        read_only_fields = fields


class SessionsWorkoutReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un plan d'entraînement (``id``, ``name``)."""

    class Meta:
        model = Workout
        fields = ("id", "name")
        read_only_fields = fields


class SessionsMuscleReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un muscle (``id``, ``name``, ``muscle_group``)."""

    class Meta:
        model = Muscle
        fields = ("id", "name", "muscle_group")
        read_only_fields = fields


class SessionsDeviceModelReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un modèle de capteur (``id``, ``manufacturer``, ``name``)."""

    class Meta:
        model = DeviceModel
        fields = ("id", "manufacturer", "name")
        read_only_fields = fields


class SessionsDeviceReferenceSerializer(serializers.ModelSerializer):
    """Référence compacte d'un capteur (``id``, nom, modèle)."""

    device_model = SessionsDeviceModelReferenceSerializer(read_only=True)

    class Meta:
        model = Device
        fields = ("id", "name", "device_model")
        read_only_fields = fields


class SessionChannelSerializer(serializers.ModelSerializer):
    """Lecture d'un canal de séance (muscle/côté figés, calibration gelée)."""

    device = SessionsDeviceReferenceSerializer(read_only=True)
    muscle = SessionsMuscleReferenceSerializer(read_only=True)

    class Meta:
        model = SessionChannel
        fields = (
            "id",
            "device",
            "channel_id",
            "muscle",
            "side",
            "data_type",
            "units",
            "calibration",
        )
        read_only_fields = fields


class SessionDeviceSerializer(serializers.ModelSerializer):
    """Lecture d'un appareil de séance (rôle + décalage d'horloge, feature 07)."""

    device = SessionsDeviceReferenceSerializer(read_only=True)

    class Meta:
        model = SessionDevice
        fields = ("id", "device", "role", "clock_offset_ms")
        read_only_fields = fields


class SessionListSerializer(serializers.ModelSerializer):
    """Séance en liste : références compactes, sans canaux ni annotations.

    ``warnings`` est calculé ici aussi (et pas seulement dans le détail) : un
    client qui ne fait que lister sait déjà qu'une séance a été créée sans
    placement déclaré.
    """

    athlete = SessionsAthleteReferenceSerializer(read_only=True)
    setup = SessionsSetupReferenceSerializer(read_only=True)
    exercise = SessionsExerciseReferenceSerializer(read_only=True)
    workout = SessionsWorkoutReferenceSerializer(read_only=True)
    warnings = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = (
            "id",
            "athlete",
            "session_type",
            "setup",
            "setup_declared",
            "exercise",
            "workout",
            "status",
            "source",
            "protocol_version",
            "started_at",
            "ended_at",
            "calibration_type",
            "created_at",
            "warnings",
        )
        read_only_fields = fields

    def get_warnings(self, obj) -> list[str]:
        return [] if obj.setup_declared else ["setup_not_declared"]


class SessionDetailSerializer(SessionListSerializer):
    """Détail d'une séance : + canaux, appareils, annotations et ``editable``.

    ``warnings`` reprend la même règle que la liste (et que la réponse de
    création) — spec 06 : l'avertissement ``setup_not_declared`` est renvoyé
    « dans la réponse ET le détail ».
    """

    channels = SessionChannelSerializer(many=True, read_only=True)
    devices = SessionDeviceSerializer(many=True, read_only=True)
    annotations = serializers.SerializerMethodField()
    editable = serializers.SerializerMethodField()

    class Meta(SessionListSerializer.Meta):
        fields = SessionListSerializer.Meta.fields + (
            "notes",
            "acquisition_config",
            "channels",
            "devices",
            "annotations",
            "editable",
        )
        read_only_fields = fields

    def get_annotations(self, obj) -> list[dict]:
        # Résolu au moment de l'appel (AnnotationSerializer est défini plus bas).
        return AnnotationSerializer(obj.annotations.all(), many=True).data

    def get_editable(self, obj) -> bool:
        request = self.context.get("request")
        if request is None or not getattr(request.user, "is_authenticated", False):
            return False
        from apps.sessions import selectors

        return selectors.can_write_session(request.user, obj)


class SessionChannelInputSerializer(serializers.Serializer):
    """Déclaration manuelle d'un canal (création sans setup, ou ``PUT /channels/``).

    ``device`` est OBLIGATOIRE sur chaque canal ; les canaux d'un même appareil
    sont distincts (``(session, device, channel_id)`` unique — contrôlé ici pour
    renvoyer une erreur de forme propre plutôt qu'une contrainte de base).
    """

    device = serializers.PrimaryKeyRelatedField(queryset=Device.objects.all())
    channel_id = serializers.IntegerField(min_value=1)
    muscle = serializers.PrimaryKeyRelatedField(queryset=Muscle.objects.all())
    side = serializers.ChoiceField(
        choices=SessionChannel.Side.choices, default=SessionChannel.Side.NA
    )
    data_type = serializers.ChoiceField(
        choices=SessionChannel.DataType.choices, default=SessionChannel.DataType.EMG_RAW
    )
    units = serializers.CharField(required=False, allow_blank=True, default="")

    @staticmethod
    def _entries_accumulator(field):
        """Remonte la chaîne de parents jusqu'au sérialiseur porteur de l'accumulateur.

        Avec ``many=True``, le parent DIRECT d'une entrée est la
        ``ListSerializer`` (qui n'a pas d'accumulateur) ; c'est le
        sérialiseur qui déclare le champ (``SessionCreateSerializer`` /
        ``ReplaceChannelsSerializer``) qui en porte un, plus haut dans la chaîne.
        """
        node = field.parent
        while node is not None:
            entries = getattr(node, "_channel_entries", None)
            if entries is not None:
                return entries
            node = getattr(node, "parent", None)
        return None

    def validate(self, attrs):
        # Les entrées d'une liste ``many=True`` sont validées séquentiellement :
        # chaque entrée validée est accumulée par le sérialiseur porteur du
        # champ, ce qui permet de refuser les dupliqués ``(device, channel_id)``.
        entries = self._entries_accumulator(self)
        if entries is not None:
            device_pk = attrs["device"].pk
            channel_id = attrs["channel_id"]
            for other in entries:
                if other["device"].pk == device_pk and other["channel_id"] == channel_id:
                    raise serializers.ValidationError(
                        "Les canaux d'un même appareil doivent être distincts."
                    )
            entries.append(attrs)
        return attrs


class SessionCreateSerializer(serializers.Serializer):
    """Création d'une séance (``POST /api/v1/sessions/``).

    - ``athlete`` requis : le droit du créateur sur ce sportif (scope
      ``sessions:write``) est contrôlé en service par ``core.access`` ;
    - avec ``setup`` : les canaux sont copiés depuis lui — la déclaration
      manuelle de ``channels`` est REFUSÉE (400) si un setup est fourni ;
    - sans ``setup`` : ``setup_declared = False``, avertissement
      ``setup_not_declared``, canaux déclarables à la main (ou absents) ;
    - validation croisée : une séance ``calibration`` exige ``setup`` ET
      ``calibration_type`` (400 sinon — une calibration sans placement connu
      n'est pas exploitable).
    """

    athlete = serializers.PrimaryKeyRelatedField(queryset=AthleteProfile.objects.all())
    session_type = serializers.ChoiceField(choices=Session.SessionType.choices)
    setup = serializers.PrimaryKeyRelatedField(
        queryset=SensorSetup.objects.all(), required=False, allow_null=True, default=None
    )
    # Mêmes valeurs que ``Calibration.type`` (feature 05b) — source unique.
    calibration_type = serializers.ChoiceField(
        choices=Calibration.Type.choices, required=False, allow_null=True, default=None
    )
    exercise = serializers.PrimaryKeyRelatedField(
        queryset=Exercise.objects.all(), required=False, allow_null=True, default=None
    )
    workout = serializers.PrimaryKeyRelatedField(
        queryset=Workout.objects.all(), required=False, allow_null=True, default=None
    )
    source = serializers.ChoiceField(choices=Session.Source.choices, default=Session.Source.MOBILE)
    protocol_version = serializers.IntegerField(min_value=1, default=1)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    acquisition_config = serializers.JSONField(required=False, default=dict)
    channels = SessionChannelInputSerializer(many=True, required=False, default=list)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._channel_entries = []  # accumulateur de dupliqués (device, channel_id)

    def validate(self, attrs):
        session_type = attrs["session_type"]
        setup = attrs.get("setup")
        calibration_type = attrs.get("calibration_type")
        if session_type == Session.SessionType.CALIBRATION:
            errors = {}
            if setup is None:
                errors["setup"] = ["Une séance de calibration exige un setup (placement connu)."]
            if not calibration_type:
                errors["calibration_type"] = [
                    "Une séance de calibration exige un ``calibration_type``."
                ]
            if errors:
                raise serializers.ValidationError(errors)
        if setup is not None and attrs.get("channels"):
            raise serializers.ValidationError(
                {
                    "channels": [
                        "Les canaux sont copiés depuis le setup fourni ; la déclaration "
                        "manuelle n'est possible que sans setup."
                    ]
                }
            )
        return attrs


class SessionUpdateSerializer(serializers.Serializer):
    """Mise à jour partielle d'une séance (``PATCH /api/v1/sessions/{id}/``).

    Seuls ``notes`` et ``acquisition_config`` sont modifiables — et uniquement
    pendant ``created`` (contrôlé en service, ``locked`` 409). Le statut ne
    passe JAMAIS par un sérialiseur : transitions dédiées
    (``/start/``, ``/complete/``, ``/cancel/``).
    """

    notes = serializers.CharField(required=False, allow_blank=True)
    acquisition_config = serializers.JSONField(required=False)


class ReplaceChannelsSerializer(serializers.Serializer):
    """Remplacement intégral des canaux (``PUT /sessions/{id}/channels/``).

    ``channels`` est la liste COMPLÈTE des canaux de la séance : le service les
    remplace atomiquement et re-dérive les appareils (premier appareil distinct
    = primaire). Uniquement pendant ``created`` (``locked``, 409).
    """

    channels = SessionChannelInputSerializer(many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._channel_entries = []  # accumulateur de dupliqués (device, channel_id)


class SessionDeviceInputSerializer(serializers.Serializer):
    """Entrée de la liste intégrale des appareils (capteur + rôle)."""

    device = serializers.PrimaryKeyRelatedField(queryset=Device.objects.all())
    role = serializers.ChoiceField(
        choices=SessionDevice.Role.choices, default=SessionDevice.Role.PRIMARY
    )


class ReplaceDevicesSerializer(serializers.Serializer):
    """Remplacement intégral des rôles d'appareils (``PUT /sessions/{id}/devices/``).

    ``devices`` est la liste COMPLÈTE des appareils de la séance avec leur rôle :
    l'ensemble doit être exactement celui référencé par les canaux (l'ajout ou le
    retrait d'un appareil passe par ``PUT /channels/``) ; au plus un primaire.
    Uniquement pendant ``created`` (``locked``, 409).
    """

    devices = SessionDeviceInputSerializer(many=True)

    def validate_devices(self, value: list) -> list:
        seen: set = set()
        for entry in value:
            device_pk = entry["device"].pk
            if device_pk in seen:
                raise serializers.ValidationError(
                    "Un même appareil ne peut apparaître qu'une fois dans la liste."
                )
            seen.add(device_pk)
        return value


class AnnotationSerializer(serializers.ModelSerializer):
    """Lecture d'une annotation (tri par ``offset_ms``, puis ``created_at``).

    ``author`` n'est JAMAIS exposé (ni pk ni email) : l'accès à une annotation
    est l'accès à la séance ; l'auteur reste une donnée interne.
    """

    class Meta:
        model = SessionAnnotation
        fields = ("id", "kind", "offset_ms", "text", "metadata", "created_at")
        read_only_fields = fields


class AnnotationCreateSerializer(serializers.Serializer):
    """Création d'une annotation (``POST /sessions/{id}/annotations/``).

    ``kind`` validé par choices du modèle ; ``offset_ms`` positionne le marqueur
    par rapport au début d'acquisition (horloge de l'appareil primaire). Le
    statut de la séance (``recording`` ou ``completed``) est contrôlé en service.
    """

    kind = serializers.ChoiceField(choices=SessionAnnotation.Kind.choices)
    offset_ms = serializers.IntegerField()
    text = serializers.CharField(required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)


class AnnotationUpdateSerializer(serializers.Serializer):
    """Mise à jour partielle d'une annotation (``PATCH .../annotations/{aid}/``).

    ``session``, ``author`` et ``created_at`` ne sont jamais modifiables.
    """

    kind = serializers.ChoiceField(choices=SessionAnnotation.Kind.choices, required=False)
    offset_ms = serializers.IntegerField(required=False)
    text = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)


class SuggestedSetupSerializer(serializers.Serializer):
    """Réponse de ``GET /athletes/{id}/sessions/suggested-setup/``.

    ``setup`` est la référence compacte du placement de la DERNIÈRE séance du
    sportif (proposition « même placement que la dernière fois ? ») — ou
    ``null`` si le sportif n'a pas encore de séance, ou si sa dernière séance a
    été créée sans setup (rien à proposer).
    """

    setup = SessionsSetupReferenceSerializer(allow_null=True)
