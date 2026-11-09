"""Vues de la feature 06 (app ``sessions``).

- ``GET/POST /api/v1/sessions/`` : liste des séances visibles (sélecteur
  ``apps.sessions.selectors.visible_sessions``) avec filtres (sportif, statut,
  dates, exercice, appareil, type de séance, placement déclaré) et création
  pour un sportif rattaché (contrôlé en service, scope ``sessions:write``) ;
- ``GET/PATCH /api/v1/sessions/{id}/`` : détail visible selon
  ``selectors.can_read_session`` (404 sinon — l'existence n'est pas révélée,
  même convention que les features 03/04/05) ; PATCH limité à ``notes`` /
  ``acquisition_config`` pendant ``created`` (``locked``, 409) ;
- ``POST /api/v1/sessions/{id}/start|complete|cancel/`` : transitions de la
  machine à états, EXCLUSIVEMENT via les services dédiés (verrouillage
  ``select_for_update``) — le statut ne passe jamais par un sérialiseur ;
- ``GET/PUT /api/v1/sessions/{id}/channels/`` et ``/devices/`` : lecture et
  remplacement intégral pendant ``created`` (les appareils sont re-dérivés des
  canaux au premier appareil distinct = primaire) ;
- ``GET/POST .../annotations/``, ``PATCH/DELETE .../annotations/{aid}/`` :
  annotations / marqueurs — autorisées pendant ``recording`` et après
  ``completed``, jamais sur ``cancelled`` (``annotation_blocked``, 409) ;
- ``GET /api/v1/athletes/{id}/sessions/suggested-setup/`` : setup de la
  dernière séance du sportif (route imbriquée hébergée par l'app ``athletes``).

Audit (même principe que les features 03/04/05b) : toute lecture par un
NON-propriétaire émet un événement (``session.viewed`` / ``session.listed``)
via ``apps.audit.services.record_event`` ; les transitions de statut sont aussi
tracées pour TOUS les acteurs (mutations sensibles — même convention que
``calibration.invalidated``). La metadata ne contient que des compteurs, aucune
donnée personnelle.
"""

import django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, permissions, status
from rest_framework.response import Response

from apps.audit.services import record_event
from apps.sessions import selectors, serializers, services
from apps.sessions.models import Session, SessionAnnotation, SessionChannel, SessionDevice
from core.exceptions import error_response

_ERROR_STATUS = {
    "forbidden": status.HTTP_403_FORBIDDEN,
    "not_found": status.HTTP_404_NOT_FOUND,
    "invalid_transition": status.HTTP_409_CONFLICT,
    "capability_exceeded": status.HTTP_409_CONFLICT,
    "annotation_blocked": status.HTTP_409_CONFLICT,
    "setup_incomplete": status.HTTP_409_CONFLICT,
    "locked": status.HTTP_409_CONFLICT,
    "device_not_in_session": status.HTTP_409_CONFLICT,
    "channels_reference_device": status.HTTP_409_CONFLICT,
}


def _service_error(exc: services.SessionsServiceError) -> Response:
    return error_response(_ERROR_STATUS[exc.code], code=exc.code, message=exc.message)


def _is_owner(user, session) -> bool:
    """La séance est-elle rattachée au profil du demandeur (pas de traçage alors) ?"""
    return session.athlete.user_id == user.pk


def _get_visible_session(user, pk):
    """Séance d'une route imbriquée ; 404 si elle est inaccessible.

    Même convention que les features 03/04/05 : une séance inconnue OU non
    lisible par le demandeur renvoie indistinctement 404 — son existence n'est
    jamais révélée. L'écriture (transitions, annotations) est ensuite contrôlée
    en service (scope ``sessions:write``).
    """
    session = (
        Session.objects.select_related("athlete", "setup", "exercise", "workout")
        .prefetch_related(
            "channels__device__device_model",
            "channels__muscle",
            "devices__device__device_model",
            "annotations",
        )
        .filter(pk=pk)
        .first()
    )
    if session is None or not selectors.can_read_session(user, session):
        raise exceptions.NotFound("Séance introuvable.")
    return session


def _get_visible_athlete(user, pk):
    """Profil du sportif d'une route imbriquée ; 404 s'il est inaccessible.

    Porte d'entrée de ``/athletes/{id}/sessions/suggested-setup/`` : même
    convention que les routes imbriquées 05b — un profil inconnu ou non couvert
    par un grant actif au scope ``sessions:read`` renvoie 404, sans révéler son
    existence.
    """
    from apps.athletes.models import AthleteProfile
    from core import access, scopes

    profile = AthleteProfile.objects.filter(pk=pk).first()
    if profile is None or not access.can_access_athlete(user, profile, scopes.SESSIONS_READ.name):
        raise exceptions.NotFound("Profil introuvable.")
    return profile


class SessionFilter(django_filters.FilterSet):
    """Filtres de la liste des séances.

    - ``athlete`` / ``exercise`` / ``device`` : uuid (l'appareil filtre sur les
      ``SessionDevice`` de la séance — une séance multi-appareils passe si
      l'un de ses appareils correspond) ;
    - ``status`` / ``session_type`` : valeurs des choices du modèle ;
    - ``created_at_from`` / ``created_at_to`` : bornes de dates (jour inclus)
      sur la date de création de la séance ;
    - ``setup_declared`` : ``true`` / ``false`` (séance sans placement déclaré).
    """

    athlete = django_filters.UUIDFilter(field_name="athlete_id")
    status = django_filters.ChoiceFilter(choices=Session.Status.choices)
    created_at_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_at_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    exercise = django_filters.UUIDFilter(field_name="exercise_id")
    device = django_filters.UUIDFilter(field_name="devices__device_id")
    session_type = django_filters.ChoiceFilter(choices=Session.SessionType.choices)
    setup_declared = django_filters.BooleanFilter()

    class Meta:
        model = Session
        fields = (
            "athlete",
            "status",
            "created_at_from",
            "created_at_to",
            "exercise",
            "device",
            "session_type",
            "setup_declared",
        )


class SessionListView(generics.ListCreateAPIView):
    """Liste des séances visibles + création d'une séance pour un sportif."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.SessionListSerializer
    filterset_class = SessionFilter

    def get_queryset(self):
        return selectors.visible_sessions(self.request.user).select_related(
            "athlete", "setup", "exercise", "workout"
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        granted_count = queryset.exclude(athlete__user=request.user).count()
        if granted_count:
            record_event(
                request.user,
                "session.listed",
                None,
                metadata={"granted_sessions": granted_count},
                request=request,
            )
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = serializers.SessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session, warnings = services.create_session(request.user, serializer.validated_data)
        except services.SessionsServiceError as exc:
            return _service_error(exc)
        output = serializers.SessionDetailSerializer(session, context={"request": request}).data
        # Spec 06 : l'avertissement ``setup_not_declared`` est renvoyé dans la
        # RÉPONSE de création (et pas seulement dans le détail).
        output["warnings"] = warnings
        return Response(output, status=status.HTTP_201_CREATED)


class SessionDetailView(generics.RetrieveUpdateAPIView):
    """Détail d'une séance visible + mise à jour pendant ``created``.

    PATCH limité à ``notes`` / ``acquisition_config`` (contrôlé en service —
    ``locked``, 409 hors ``created``) ; le statut ne passe JAMAIS par un
    sérialiseur (transitions dédiées ci-dessous).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.SessionDetailSerializer
    http_method_names = ["get", "patch"]  # pas de PUT/DELETE : périmètre API

    def get_object(self):
        return _get_visible_session(self.request.user, self.kwargs["pk"])

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if not _is_owner(request.user, instance):
            record_event(
                request.user,
                "session.viewed",
                instance,
                athlete=instance.athlete,
                request=request,
            )
        return super().retrieve(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.SessionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = services.update_session(request.user, instance.pk, serializer.validated_data)
        except services.SessionsServiceError as exc:
            return _service_error(exc)
        output = serializers.SessionDetailSerializer(session, context={"request": request})
        return Response(output.data)


class SessionStartView(generics.GenericAPIView):
    """Démarrage d'une séance (``POST .../start/``) : ``created → recording``."""

    permission_classes = [permissions.IsAuthenticated]
    queryset = Session.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["post"]

    def get_object(self):
        return _get_visible_session(self.request.user, self.kwargs["pk"])

    @extend_schema(
        operation_id="sessions_start",
        request=None,  # pas de corps : la transition est portée par l'URL
        responses={status.HTTP_200_OK: serializers.SessionDetailSerializer},
    )
    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            session = services.start_session(request.user, instance.pk)
        except services.SessionsServiceError as exc:
            return _service_error(exc)
        record_event(
            request.user, "session.started", session, athlete=session.athlete, request=request
        )
        output = serializers.SessionDetailSerializer(session, context={"request": request})
        return Response(output.data)


class SessionCompleteView(generics.GenericAPIView):
    """Fin d'une séance (``POST .../complete/``) : ``recording → completed``.

    Le hook ``on_session_completed`` est appelé en service APRÈS le commit —
    vide en feature 06, branché en features 07 et 09.
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = Session.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["post"]

    def get_object(self):
        return _get_visible_session(self.request.user, self.kwargs["pk"])

    @extend_schema(
        operation_id="sessions_complete",
        request=None,  # pas de corps : la transition est portée par l'URL
        responses={status.HTTP_200_OK: serializers.SessionDetailSerializer},
    )
    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            session = services.complete_session(request.user, instance.pk)
        except services.SessionsServiceError as exc:
            return _service_error(exc)
        record_event(
            request.user, "session.completed", session, athlete=session.athlete, request=request
        )
        output = serializers.SessionDetailSerializer(session, context={"request": request})
        return Response(output.data)


class SessionCancelView(generics.GenericAPIView):
    """Annulation d'une séance (``POST .../cancel/``) : ``created | recording → cancelled``."""

    permission_classes = [permissions.IsAuthenticated]
    queryset = Session.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["post"]

    def get_object(self):
        return _get_visible_session(self.request.user, self.kwargs["pk"])

    @extend_schema(
        operation_id="sessions_cancel",
        request=None,  # pas de corps : la transition est portée par l'URL
        responses={status.HTTP_200_OK: serializers.SessionDetailSerializer},
    )
    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            session = services.cancel_session(request.user, instance.pk)
        except services.SessionsServiceError as exc:
            return _service_error(exc)
        record_event(
            request.user, "session.cancelled", session, athlete=session.athlete, request=request
        )
        output = serializers.SessionDetailSerializer(session, context={"request": request})
        return Response(output.data)


class SessionChannelListUpdateView(generics.GenericAPIView):
    """Canaux d'une séance : lecture (GET) et remplacement ATOMIQUE (PUT).

    Le corps de la demande est ``{"channels": [...]}`` — liste COMPLÈTE des
    canaux (``device`` obligatoire sur chaque canal, doublons
    ``(device, channel_id)`` refusés en validation) ; le service re-dérive les
    lignes ``SessionDevice`` (premier appareil distinct = primaire). Uniquement
    pendant ``created`` (``locked``, 409). La lecture par un non-propriétaire
    est tracée (``session.viewed``).
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = SessionChannel.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["get", "put"]

    def get_object(self):
        return _get_visible_session(self.request.user, self.kwargs["pk"])

    @extend_schema(
        operation_id="sessions_channels_list",
        responses={status.HTTP_200_OK: serializers.SessionChannelSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        if not _is_owner(request.user, instance):
            record_event(
                request.user, "session.viewed", instance, athlete=instance.athlete, request=request
            )
        channels = instance.channels.select_related("muscle", "device__device_model").all()
        output = serializers.SessionChannelSerializer(
            channels, many=True, context={"request": request}
        )
        return Response(output.data)

    @extend_schema(
        operation_id="sessions_channels_replace",
        request=serializers.ReplaceChannelsSerializer,
        responses={status.HTTP_200_OK: serializers.SessionChannelSerializer(many=True)},
    )
    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.ReplaceChannelsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = services.replace_channels(
                request.user, instance.pk, serializer.validated_data["channels"]
            )
        except services.SessionsServiceError as exc:
            return _service_error(exc)
        channels = session.channels.select_related("muscle", "device__device_model").all()
        output = serializers.SessionChannelSerializer(
            channels, many=True, context={"request": request}
        )
        return Response(output.data)


class SessionDeviceListUpdateView(generics.GenericAPIView):
    """Appareils d'une séance : lecture (GET) et remplacement intégral des RÔLES (PUT).

    Le corps de la demande est ``{"devices": [{"device", "role"}...]}`` —
    l'ensemble fourni doit être EXACTEMENT celui référencé par les canaux
    (l'ajout ou le retrait d'un appareil passe par ``PUT /channels/``), au plus
    un primaire. Uniquement pendant ``created`` (``locked``, 409). La lecture
    par un non-propriétaire est tracée (``session.viewed``).
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = SessionDevice.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["get", "put"]

    def get_object(self):
        return _get_visible_session(self.request.user, self.kwargs["pk"])

    @extend_schema(
        operation_id="sessions_devices_list",
        responses={status.HTTP_200_OK: serializers.SessionDeviceSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        if not _is_owner(request.user, instance):
            record_event(
                request.user, "session.viewed", instance, athlete=instance.athlete, request=request
            )
        devices = instance.devices.select_related("device__device_model").all()
        output = serializers.SessionDeviceSerializer(
            devices, many=True, context={"request": request}
        )
        return Response(output.data)

    @extend_schema(
        operation_id="sessions_devices_replace",
        request=serializers.ReplaceDevicesSerializer,
        responses={status.HTTP_200_OK: serializers.SessionDeviceSerializer(many=True)},
    )
    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.ReplaceDevicesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = services.replace_devices(
                request.user, instance.pk, serializer.validated_data["devices"]
            )
        except services.SessionsServiceError as exc:
            return _service_error(exc)
        devices = session.devices.select_related("device__device_model").all()
        output = serializers.SessionDeviceSerializer(
            devices, many=True, context={"request": request}
        )
        return Response(output.data)


def _get_visible_annotation(user, session_pk: str, annotation_pk: str) -> SessionAnnotation:
    """Annotation d'une route imbriquée ; 404 si elle est inaccessible.

    Une annotation ne se lit que PAR SA SÉANCE : elle doit appartenir à une
    séance visible par le demandeur — sinon 404 indistinct, sans révéler son
    existence (même convention que les features 03/04/05). L'écriture est
    ensuite contrôlée en service (scope ``sessions:write`` + statut de la
    séance).
    """
    session = _get_visible_session(user, session_pk)
    annotation = session.annotations.filter(pk=annotation_pk).first()
    if annotation is None:
        raise exceptions.NotFound("Annotation introuvable.")
    return annotation


class SessionAnnotationListView(generics.ListCreateAPIView):
    """Annotations d'une séance : liste triée par ``offset_ms`` + création.

    Création autorisée pendant ``recording`` et après ``completed`` (corrections
    du coach), jamais sur ``cancelled`` (``annotation_blocked``, 409) — contrôlé
    en service sous verrouillage. La lecture par un non-propriétaire est tracée
    (``session.viewed``).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.AnnotationSerializer
    queryset = SessionAnnotation.objects.none()  # pour drf-spectacular (inférence modèle)

    def get_object(self):
        return _get_visible_session(self.request.user, self.kwargs["pk"])

    def get_queryset(self):
        return self.get_object().annotations.all()

    def list(self, request, *args, **kwargs):
        instance = self.get_object()
        if not _is_owner(request.user, instance):
            record_event(
                request.user, "session.viewed", instance, athlete=instance.athlete, request=request
            )
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.AnnotationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            annotation = services.create_annotation(
                request.user, instance.pk, serializer.validated_data
            )
        except services.SessionsServiceError as exc:
            return _service_error(exc)
        output = serializers.AnnotationSerializer(annotation, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class SessionAnnotationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Détail d'une annotation + mise à jour / suppression.

    ``PATCH`` limité à ``kind`` / ``offset_ms`` / ``text`` / ``metadata``
    (``session``, ``author`` et ``created_at`` ne sont jamais modifiables) ;
    mêmes règles de statut que la création (``annotation_blocked``, 409 sur une
    séance annulée).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.AnnotationSerializer
    http_method_names = ["get", "patch", "delete"]  # pas de PUT : périmètre API

    def get_object(self):
        return _get_visible_annotation(self.request.user, self.kwargs["pk"], self.kwargs["aid"])

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if not _is_owner(request.user, instance.session):
            record_event(
                request.user,
                "session.viewed",
                instance.session,
                athlete=instance.session.athlete,
                request=request,
            )
        return super().retrieve(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.AnnotationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            annotation = services.update_annotation(
                request.user, instance.pk, serializer.validated_data
            )
        except services.SessionsServiceError as exc:
            return _service_error(exc)
        output = serializers.AnnotationSerializer(annotation, context={"request": request})
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            services.delete_annotation(request.user, instance.pk)
        except services.SessionsServiceError as exc:
            return _service_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AthleteSuggestedSetupView(generics.GenericAPIView):
    """Setup de la dernière séance d'un sportif (``GET /athletes/{id}/sessions/suggested-setup/``).

    Proposition « même placement que la dernière fois ? » : renvoie la
    référence compacte du setup de la DERNIÈRE séance du sportif — ou
    ``{"setup": null}`` s'il n'en a pas encore, ou si sa dernière séance a été
    créée sans setup. 404 si le profil est inconnu ou non couvert par un grant
    actif au scope ``sessions:read`` (même convention que les routes imbriquées
    05b). La lecture par un non-propriétaire est tracée (``session.viewed`` sur
    la séance concernée).
    """

    permission_classes = [permissions.IsAuthenticated]
    queryset = Session.objects.none()  # pour drf-spectacular (inférence modèle)
    http_method_names = ["get"]

    @extend_schema(
        operation_id="athletes_sessions_suggested_setup",
        responses={status.HTTP_200_OK: serializers.SuggestedSetupSerializer},
    )
    def get(self, request, *args, **kwargs):
        profile = _get_visible_athlete(request.user, self.kwargs["athlete_pk"])
        # Ordre par défaut du modèle : ``-created_at`` — la première est la dernière.
        latest = Session.objects.filter(athlete=profile).select_related("setup").first()
        if latest is not None and not _is_owner(request.user, latest):
            record_event(request.user, "session.viewed", latest, athlete=profile, request=request)
        setup = latest.setup if latest is not None else None
        return Response(serializers.SuggestedSetupSerializer({"setup": setup}).data)
