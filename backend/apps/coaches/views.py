"""Vues de la feature 03 (app ``coaches``).

- ``GET /api/v1/coaches/`` : annuaire des coachs, consultable par tout
  utilisateur authentifié (un sportif doit pouvoir choisir à qui accorder
  l'accès) — filtrable par organisation ;
- ``POST /api/v1/coaches/`` : création à la demande du profil coach de
  l'utilisateur connecté (pas de nouveau compte) ;
- ``GET/PATCH /api/v1/coaches/{id}/`` : détail + mise à jour par le
  propriétaire.

L'email n'est jamais exposé (donnée personnelle).
"""

import django_filters
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.coaches import serializers, services
from apps.coaches.models import CoachProfile
from core.exceptions import error_response

_ERROR_STATUS = {
    "forbidden": status.HTTP_403_FORBIDDEN,
    "conflict": status.HTTP_409_CONFLICT,
}


def _service_error(exc: services.CoachesServiceError) -> Response:
    return error_response(_ERROR_STATUS[exc.code], code=exc.code, message=exc.message)


class CoachFilter(django_filters.FilterSet):
    """Filtre de l'annuaire : organisation (insensible à la casse)."""

    organization_name = django_filters.CharFilter(
        field_name="organization_name", lookup_expr="icontains"
    )

    class Meta:
        model = CoachProfile
        fields = ("organization_name",)


class CoachListView(generics.ListCreateAPIView):
    """Annuaire des coachs + création du propre profil coach."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.CoachProfileSerializer
    filterset_class = CoachFilter

    def get_queryset(self):
        return CoachProfile.objects.select_related("user").all()

    def create(self, request, *args, **kwargs):
        serializer = serializers.CreateCoachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = services.create_own_profile(request.user, serializer.validated_data)
        except services.CoachesServiceError as exc:
            return _service_error(exc)
        output = serializers.CoachProfileSerializer(profile, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class CoachDetailView(generics.RetrieveUpdateAPIView):
    """Détail d'un profil coach + mise à jour par le propriétaire."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.CoachProfileSerializer

    def get_queryset(self):
        return CoachProfile.objects.select_related("user").all()

    def get_object(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            profile = services.update_own_profile(request.user, instance, serializer.validated_data)
        except services.CoachesServiceError as exc:
            return _service_error(exc)
        output = serializers.CoachProfileSerializer(profile, context={"request": request})
        return Response(output.data)
