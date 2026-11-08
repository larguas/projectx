"""Vues de la feature 03 (app ``athletes``).

- ``GET /api/v1/athletes/`` : profils visibles par l'utilisateur (le sien +
  ceux couverts par un grant actif, cf. ``core.access.granted_athletes``) ;
  côté coach, cette liste ne contient donc QUE les sportifs autorisés ;
- ``POST /api/v1/athletes/`` : création à la demande du profil de
  l'utilisateur connecté (pas à l'inscription) ;
- ``GET/PATCH /api/v1/athletes/{id}/`` : détail visible selon
  ``core.access.can_see_athlete`` (404 sinon — l'existence n'est pas révélée),
  mise à jour réservée au propriétaire.

Audit : toute lecture par un non-propriétaire (coach ou membre d'équipe)
émet un événement (``athlete.viewed`` / ``athlete.listed``) via
``apps.audit.services.record_event`` ; la metadata ne contient que des
compteurs, aucune donnée personnelle.
"""

from rest_framework import exceptions, generics, permissions, status
from rest_framework.response import Response

from apps.athletes import serializers, services
from apps.audit.services import record_event
from core import access
from core.exceptions import error_response

_ERROR_STATUS = {
    "forbidden": status.HTTP_403_FORBIDDEN,
    "conflict": status.HTTP_409_CONFLICT,
}


def _service_error(exc: services.AthletesServiceError) -> Response:
    return error_response(_ERROR_STATUS[exc.code], code=exc.code, message=exc.message)


class AthleteListView(generics.ListCreateAPIView):
    """Liste des sportifs visibles + création du propre profil."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.AthleteProfileSerializer
    filterset_fields = ("sport", "sex")

    def get_queryset(self):
        return access.granted_athletes(self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        granted_count = queryset.exclude(user=request.user).count()
        if granted_count:
            record_event(
                request.user,
                "athlete.listed",
                None,
                metadata={"granted_athletes": granted_count},
                request=request,
            )
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = serializers.CreateAthleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = services.create_own_profile(request.user, serializer.validated_data)
        except services.AthletesServiceError as exc:
            return _service_error(exc)
        output = serializers.AthleteProfileSerializer(profile, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class AthleteDetailView(generics.RetrieveUpdateAPIView):
    """Détail d'un profil sportif visible + mise à jour par le propriétaire."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.AthleteProfileSerializer

    def get_object(self):
        from apps.athletes.models import AthleteProfile

        profile = AthleteProfile.objects.filter(pk=self.kwargs["pk"]).first()
        if profile is None or not access.can_see_athlete(self.request.user, profile):
            raise exceptions.NotFound("Profil introuvable.")
        return profile

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.user_id != request.user.pk:
            record_event(
                request.user, "athlete.viewed", instance, athlete=instance, request=request
            )
        return super().retrieve(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            profile = services.update_own_profile(request.user, instance, serializer.validated_data)
        except services.AthletesServiceError as exc:
            return _service_error(exc)
        output = serializers.AthleteProfileSerializer(profile, context={"request": request})
        return Response(output.data)
