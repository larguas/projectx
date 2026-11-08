"""Vues de la feature 05b (app ``setups``).

- ``GET/POST /api/v1/setups/`` : liste des setups visibles (sélecteur
  ``apps.setups.selectors.visible_setups``) et création pour un sportif
  rattaché (contrôlé en service, scope ``setups:write``) ;
- ``GET/PATCH/DELETE /api/v1/setups/{id}/`` : détail visible selon
  ``selectors.can_read_setup`` (404 sinon — l'existence n'est pas révélée,
  même convention que les features 03/04/05) ; PATCH et DELETE refusés si le
  setup est utilisé (``setup_frozen``, 409) ;
- ``POST /api/v1/setups/{id}/new-version/`` : version n+1 (lignée ``parent``),
  corps ``{"placement_unchanged": bool}`` ;
- ``GET/PUT /api/v1/setups/{id}/channels/`` : lecture et remplacement ATOMIQUE
  de la liste COMPLÈTE des canaux (doublons ``(device, channel_id)`` refusés) ;
- ``GET /api/v1/setups/compare/?a={id}&b={id}`` : niveau de comparabilité
  (``{level, reasons[]}``) ; un setup absent ou non lisible compte comme absent
  (niveau ``unknown`` — l'existence n'est pas révélée) ;
- ``GET /api/v1/athletes/{id}/setups/current/`` : versions courantes du
  sportif (404 si le profil est inaccessible au scope ``setups:read``) ;
- ``GET /api/v1/athletes/{id}/calibrations/`` : calibrations du sportif,
  filtres ``setup``, ``type``, ``applicable`` ;
- ``POST /api/v1/calibrations/{id}/invalidate/`` : invalidation irréversible
  (``already_invalidated``, 409 si déjà invalidée) ;
- ``GET /api/v1/muscles/{id}/placement-guide/`` : guide de placement du muscle
  (catalogue, lecture seule ; 404 si le muscle ou le guide n'existe pas).

Audit (même principe que les features 03/04/05) : toute lecture par un
NON-propriétaire émet un événement via ``apps.audit.services.record_event`` —
c'est le traçage des lectures coach/équipe exigé par la spec. Noms d'événements
décidés et stables (convention ``<resource>.viewed`` / ``<resource>.listed``) :
- ``setup.viewed`` : détail d'un setup lu par un non-propriétaire ;
- ``setup.listed`` : au moins un setup non propriétaire visible dans une liste
  (``/setups/`` ou ``/athletes/{id}/setups/current/``) ;
- ``calibration.listed`` : calibrations d'un sportif lu par un non-propriétaire ;
- ``calibration.invalidated`` : invalidation d'une calibration (le motif est
  mémorisé sur la calibration ; la metadata n'en contient pas de copie).

La metadata ne contient que des compteurs, aucune donnée personnelle.
"""

import re

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, generics, permissions, status
from rest_framework.response import Response

from apps.audit.services import record_event
from apps.setups import selectors, serializers, services
from apps.setups.models import Calibration, PlacementGuide, SensorSetup
from core.exceptions import error_response

_ERROR_STATUS = {
    "forbidden": status.HTTP_403_FORBIDDEN,
    "setup_frozen": status.HTTP_409_CONFLICT,
    "has_newer_version": status.HTTP_409_CONFLICT,
    "has_calibrations": status.HTTP_409_CONFLICT,
    "name_taken": status.HTTP_409_CONFLICT,
    "already_invalidated": status.HTTP_409_CONFLICT,
}


def _service_error(exc: services.SetupsServiceError) -> Response:
    return error_response(_ERROR_STATUS[exc.code], code=exc.code, message=exc.message)


def _get_visible_setup(user, pk):
    """Setup lisible par ``user`` ou 404 (l'existence n'est pas révélée)."""
    setup = (
        SensorSetup.objects.select_related("athlete")
        .prefetch_related("channels__muscle", "channels__device__device_model")
        .filter(pk=pk)
        .first()
    )
    if setup is None or not selectors.can_read_setup(user, setup):
        raise exceptions.NotFound("Setup introuvable.")
    return setup


def _get_visible_athlete(user, pk):
    """Profil du sportif d'une route imbriquée ; 404 s'il est inaccessible.

    Portes d'entrée des routes ``/athletes/{id}/setups/current/`` et
    ``/athletes/{id}/calibrations/`` : même convention que le détail d'un
    profil (feature 03) — un profil inconnu ou non couvert par un grant actif
    au scope ``setups:read`` renvoie 404, sans révéler son existence.
    """
    from apps.athletes.models import AthleteProfile
    from core import access, scopes

    profile = AthleteProfile.objects.filter(pk=pk).first()
    if profile is None or not access.can_access_athlete(user, profile, scopes.SETUPS_READ.name):
        raise exceptions.NotFound("Profil introuvable.")
    return profile


def _is_owner(user, setup) -> bool:
    """Le setup appartient-il au profil du demandeur (pas de traçage alors) ?"""
    return setup.athlete.user_id == user.pk


class SetupListView(generics.ListCreateAPIView):
    """Liste des setups visibles + création d'un setup pour un sportif."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.SensorSetupSerializer

    def get_queryset(self):
        return (
            selectors.visible_setups(self.request.user)
            .select_related("athlete")
            .prefetch_related("channels__muscle", "channels__device__device_model")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        granted_count = queryset.exclude(athlete__user=request.user).count()
        if granted_count:
            record_event(
                request.user,
                "setup.listed",
                None,
                metadata={"granted_setups": granted_count},
                request=request,
            )
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = serializers.CreateSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            setup = services.create_setup(request.user, serializer.validated_data)
        except services.SetupsServiceError as exc:
            return _service_error(exc)
        output = serializers.SensorSetupSerializer(setup, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class SetupDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Détail d'un setup visible + mise à jour / suppression selon les droits.

    PATCH (``name``, ``notes``) et DELETE sont refusés en service si le setup
    est utilisé par une séance (``setup_frozen``, 409) — la double vérification
    modèle passe par ``save()`` -> ``assert_editable``.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.SensorSetupSerializer
    http_method_names = ["get", "patch", "delete"]  # pas de PUT : périmètre API

    def get_object(self):
        return _get_visible_setup(self.request.user, self.kwargs["pk"])

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if not _is_owner(request.user, instance):
            record_event(
                request.user,
                "setup.viewed",
                instance,
                athlete=instance.athlete,
                request=request,
            )
        return super().retrieve(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.UpdateSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            setup = services.update_setup(request.user, instance, serializer.validated_data)
        except services.SetupsServiceError as exc:
            return _service_error(exc)
        output = serializers.SensorSetupSerializer(setup, context={"request": request})
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            services.delete_setup(request.user, instance)
        except services.SetupsServiceError as exc:
            return _service_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SetupNewVersionView(generics.GenericAPIView):
    """Nouvelle version d'un setup (``POST .../new-version/``).

    Fonctionne sur un setup UTILISÉ (c'est le seul moyen de le modifier) : la
    version source n'est jamais sauvegardée, seulement basculée en
    ``is_current=False`` par une mise à jour en base ciblée.
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = SensorSetup.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["post"]

    def get_object(self):
        return _get_visible_setup(self.request.user, self.kwargs["pk"])

    @extend_schema(
        operation_id="setups_new_version",
        request=serializers.NewVersionSerializer,
        responses={status.HTTP_201_CREATED: serializers.SensorSetupSerializer},
    )
    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.NewVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            setup = services.new_version(request.user, instance, serializer.validated_data)
        except services.SetupsServiceError as exc:
            return _service_error(exc)
        output = serializers.SensorSetupSerializer(setup, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


_CHANNEL_ENTRY_KEY = re.compile(r"^channels\[(\d+)\]\[([a-z_]+)\]$")


def _nested_channels_payload(data) -> dict:
    """Replie la forme multipart plate de ``PUT .../channels/`` en ``{"channels": [...]}``.

    DRF livre les champs de formulaire À PLAT : les clés ``channels[i][champ]``
    (dont ``photo``, un fichier) n'arrivent pas imbriquées dans
    ``request.data``. Ce helper reconstruit la structure équivalente à la forme
    JSON, pour que ``SetChannelsSerializer`` valide le même contrat quel que
    soit le format d'envoi (JSON ou multipart). Sans clé indexée (payload
    JSON), la donnée est renvoyée telle quelle ; les autres clés sont
    préservées.
    """
    entries: dict = {}
    rest: dict = {}
    for key, value in data.items():
        match = _CHANNEL_ENTRY_KEY.match(key)
        if match is None:
            rest[key] = value
            continue
        index = int(match.group(1))
        entries.setdefault(index, {})[match.group(2)] = value
    if not entries:
        return dict(data)
    return {**rest, "channels": [entries[i] for i in sorted(entries)]}


class SetupChannelsView(generics.GenericAPIView):
    """Canaux d'un setup : lecture (GET) et remplacement ATOMIQUE (PUT).

    Le corps de la demande est ``{"channels": [...]}`` — liste COMPLÈTE des
    canaux (doublons ``(device, channel_id)`` refusés en validation ; tous les
    champs détaillés optionnels — mode simple). Deux formats d'envoi sont
    acceptés : JSON, ou multipart avec des clés indexées
    ``channels[i][champ]`` (seul le format qui permet d'uploader la photo de
    chaque canal) ; les deux convergent vers le même sérialiseur. Le niveau de
    détail du setup est recalculé en service après le remplacement.
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = SensorSetup.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["get", "put"]

    def get_object(self):
        return _get_visible_setup(self.request.user, self.kwargs["pk"])

    @extend_schema(
        operation_id="setups_channels_list",
        responses={status.HTTP_200_OK: serializers.SetupChannelSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        if not _is_owner(request.user, instance):
            record_event(
                request.user,
                "setup.viewed",
                instance,
                athlete=instance.athlete,
                request=request,
            )
        channels = instance.channels.select_related("muscle", "device__device_model").all()
        output = serializers.SetupChannelSerializer(
            channels, many=True, context={"request": request}
        )
        return Response(output.data)

    @extend_schema(
        operation_id="setups_channels_replace",
        request=serializers.SetChannelsSerializer,
        responses={status.HTTP_200_OK: serializers.SetupChannelSerializer(many=True)},
    )
    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        payload = _nested_channels_payload(request.data)
        serializer = serializers.SetChannelsSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        try:
            channels = services.set_channels(
                request.user, instance, serializer.validated_data["channels"]
            )
        except services.SetupsServiceError as exc:
            return _service_error(exc)
        output = serializers.SetupChannelSerializer(
            channels, many=True, context={"request": request}
        )
        return Response(output.data)


class SetupCompareView(generics.GenericAPIView):
    """Comparabilité de deux setups (``GET /setups/compare/?a={id}&b={id}``).

    Lecture pure : le contrôle d'accès est fait ICI (pas en service) — un setup
    introuvable OU non lisible par le demandeur compte comme absent, et le
    niveau renvoyé est ``unknown`` : l'existence d'un setup non visible n'est
    jamais révélée. Les paramètres mal formés sont une erreur de demande (400).
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = SensorSetup.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["get"]

    @extend_schema(
        operation_id="setups_compare",
        parameters=[
            OpenApiParameter("a", OpenApiTypes.UUID, description="Premier setup."),
            OpenApiParameter("b", OpenApiTypes.UUID, description="Second setup."),
        ],
        responses={status.HTTP_200_OK: serializers.SetupComparisonSerializer},
    )
    def get(self, request, *args, **kwargs):
        query = serializers.CompareSetupsQuerySerializer(data=request.query_params)
        if not query.is_valid():
            return Response(query.errors, status=status.HTTP_400_BAD_REQUEST)

        def resolve(raw_id):
            setup = SensorSetup.objects.filter(pk=raw_id).first()
            if setup is None or not selectors.can_read_setup(request.user, setup):
                return None  # absent OU non visible : indistinctement « absent »
            return setup

        result = services.compare_setups(
            resolve(query.validated_data["a"]), resolve(query.validated_data["b"])
        )
        return Response(result)


class AthleteCurrentSetupsView(generics.ListAPIView):
    """Versions courantes des setups d'un sportif (``GET /athletes/{id}/setups/current/``).

    404 si le profil est inconnu ou non couvert par un grant actif au scope
    ``setups:read`` (même convention que le détail du profil, feature 03). La
    lecture par un non-propriétaire est tracée (``setup.listed``).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.SensorSetupSerializer
    queryset = SensorSetup.objects.none()  # pour drf-spectacular (inférence modèle)

    def get_queryset(self):
        return (
            selectors.visible_setups(self.request.user)
            .filter(athlete=self._profile, is_current=True)
            .select_related("athlete")
            .prefetch_related("channels__muscle", "channels__device__device_model")
        )

    def list(self, request, *args, **kwargs):
        self._profile = _get_visible_athlete(request.user, self.kwargs["athlete_pk"])
        queryset = self.filter_queryset(self.get_queryset())
        if self._profile.user_id != request.user.pk:
            granted_count = queryset.count()
            if granted_count:
                record_event(
                    request.user,
                    "setup.listed",
                    None,
                    athlete=self._profile,
                    metadata={"granted_setups": granted_count},
                    request=request,
                )
        return super().list(request, *args, **kwargs)


class AthleteCalibrationsView(generics.ListAPIView):
    """Calibrations d'un sportif (``GET /athletes/{id}/calibrations/``).

    404 si le profil est inconnu ou non couvert par un grant actif au scope
    ``setups:read`` (même convention que les autres routes imbriquées). Filtres
    optionnels : ``setup`` (uuid de la version), ``type`` (``mvc`` /
    ``rest_baseline``), ``applicable`` (``true``/``false`` — non invalidée et
    non expirée ; le rattachement au setup d'une séance relève du service
    ``applicable_calibrations``, pas d'un filtre de liste). La lecture par un
    non-propriétaire est tracée (``calibration.listed``).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.CalibrationSerializer
    queryset = Calibration.objects.none()  # pour drf-spectacular (inférence modèle)

    def get_queryset(self):
        queryset = (
            Calibration.objects.filter(athlete=self._profile)
            .select_related("athlete", "setup", "setup_channel__muscle")
            .prefetch_related("setup_channel__device__device_model")
        )
        params = serializers.AthleteCalibrationsQuerySerializer(data=self.request.query_params)
        if not params.is_valid():
            raise exceptions.ValidationError(params.errors)
        filters = params.validated_data
        if filters.get("setup") is not None:
            queryset = queryset.filter(setup_id=filters["setup"])
        if filters.get("type") is not None:
            queryset = queryset.filter(type=filters["type"])
        applicable = filters.get("applicable")
        if applicable is not None:
            now = timezone.now()
            applicable_q = Q(invalidated_at__isnull=True) & (
                Q(valid_until__isnull=True) | Q(valid_until__gt=now)
            )
            queryset = queryset.filter(applicable_q if applicable else ~applicable_q)
        return queryset

    def list(self, request, *args, **kwargs):
        self._profile = _get_visible_athlete(request.user, self.kwargs["athlete_pk"])
        queryset = self.filter_queryset(self.get_queryset())
        if self._profile.user_id != request.user.pk:
            granted_count = queryset.count()
            if granted_count:
                record_event(
                    request.user,
                    "calibration.listed",
                    None,
                    athlete=self._profile,
                    metadata={"granted_calibrations": granted_count},
                    request=request,
                )
        return super().list(request, *args, **kwargs)


class CalibrationInvalidateView(generics.GenericAPIView):
    """Invalidation d'une calibration (``POST /calibrations/{id}/invalidate/``).

    Lisible si le setup rattaché est lisible (même règle : scope ``setups:read``
    sur le profil du sportif) ; 404 sinon, sans révéler l'existence. L'écriture
    est contrôlée en service (scope ``setups:write``). L'invalidation est
    irréversible et TRACÉE pour tous les acteurs (mutation sensible — pas
    seulement les lectures non propriétaire) : événement ``calibration.invalidated``.
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = Calibration.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["post"]

    def get_object(self):
        calibration = (
            Calibration.objects.select_related("athlete", "setup__athlete", "setup_channel__muscle")
            .prefetch_related("setup_channel__device__device_model")
            .filter(pk=self.kwargs["pk"])
            .first()
        )
        if calibration is None or not selectors.can_read_setup(
            self.request.user, calibration.setup
        ):
            raise exceptions.NotFound("Calibration introuvable.")
        return calibration

    @extend_schema(
        operation_id="calibrations_invalidate",
        request=serializers.InvalidateCalibrationSerializer,
        responses={status.HTTP_200_OK: serializers.CalibrationSerializer},
    )
    def post(self, request, *args, **kwargs):
        calibration = self.get_object()
        serializer = serializers.InvalidateCalibrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            calibration = services.invalidate_calibration(
                request.user, calibration, serializer.validated_data["reason"]
            )
        except services.SetupsServiceError as exc:
            return _service_error(exc)
        record_event(
            request.user,
            "calibration.invalidated",
            calibration,
            athlete=calibration.athlete,
            request=request,
        )
        output = serializers.CalibrationSerializer(calibration, context={"request": request})
        return Response(output.data)


class PlacementGuideView(generics.GenericAPIView):
    """Guide de placement d'un muscle (``GET /muscles/{id}/placement-guide/``).

    Catalogue en lecture seule (comme les muscles, feature 05 — aucun profil
    sportif rattaché, donc pas de contrôle d'accès par grant) ; 404 si le
    muscle ou le guide n'existe pas. L'image est servie en URL relative via
    ``default_storage`` (jamais de bytes bruts).
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = PlacementGuide.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["get"]

    @extend_schema(
        operation_id="muscles_placement_guide",
        responses={status.HTTP_200_OK: serializers.PlacementGuideSerializer},
    )
    def get(self, request, *args, **kwargs):
        guide = (
            PlacementGuide.objects.select_related("muscle")
            .filter(muscle_id=kwargs["muscle_pk"])
            .first()
        )
        if guide is None:
            raise exceptions.NotFound("Guide de placement introuvable.")
        output = serializers.PlacementGuideSerializer(guide, context={"request": request})
        return Response(output.data)
