"""Vues de la feature 03 (app ``teams`` : équipes, membres, autorisations).

Routes :
- ``GET/POST /api/v1/teams/`` : mes équipes (membre actif ou en attente) +
  création (l'utilisateur devient propriétaire) ;
- ``GET/PATCH/DELETE /api/v1/teams/{id}/`` : membre pour lire, propriétaire
  pour renommer / supprimer ;
- ``GET/POST /api/v1/teams/{team_id}/members/`` : membres + invitation
  (propriétaire uniquement) ;
- ``DELETE /api/v1/teams/{team_id}/members/{user_id}/`` : retrait (propriétaire
  ou le membre lui-même) ;
- ``GET/POST /api/v1/access-grants/`` : grants que j'ai accordés + (en tant
  que coach) grants qui me sont adressés ; création réservée au propriétaire
  du profil sportif, email vérifié requis ;
- ``POST /api/v1/access-grants/{id}/accept/`` : acceptation par le coach
  bénéficiaire (email vérifié requis) ;
- ``POST /api/v1/access-grants/{id}/revoke/`` : révocation par le propriétaire
  du profil (effet immédiat).

Toutes les mutations de droits passent par ``apps.teams.services`` (et émettent
leur événement d'audit) ; les vues ne font que mapper les codes stables en
réponses HTTP.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, generics, permissions, status
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsEmailVerified
from apps.teams import serializers, services
from apps.teams.models import AccessGrant, Team, TeamMembership
from core.exceptions import error_response

_ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "forbidden": status.HTTP_403_FORBIDDEN,
    "conflict": status.HTTP_409_CONFLICT,
    "invalid_scope": status.HTTP_400_BAD_REQUEST,
    "invalid_role": status.HTTP_400_BAD_REQUEST,
    "invalid_grantee": status.HTTP_400_BAD_REQUEST,
    "invalid_expiry": status.HTTP_400_BAD_REQUEST,
    "grant_expired": status.HTTP_410_GONE,
}


def _service_error(exc: services.TeamsServiceError) -> Response:
    return error_response(_ERROR_STATUS[exc.code], code=exc.code, message=exc.message)


class TeamListView(generics.ListCreateAPIView):
    """Mes équipes (actives ou en attente) + création d'une équipe."""

    permission_classes = [permissions.IsAuthenticated]
    # Pour drf-spectacular (inférence du modèle) ; remplacé par ``get_queryset``.
    queryset = Team.objects.none()
    serializer_class = serializers.TeamSerializer

    def get_queryset(self):
        return (
            Team.objects.filter(
                memberships__user=self.request.user,
                memberships__status__in=[
                    TeamMembership.Status.ACTIVE,
                    TeamMembership.Status.PENDING,
                ],
            )
            .distinct()
            .select_related("owner")
        )

    def create(self, request, *args, **kwargs):
        serializer = serializers.CreateTeamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        team = services.create_team(request.user, serializer.validated_data["name"])
        output = serializers.TeamSerializer(team, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class TeamDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Équipe (membre pour lire ; propriétaire pour PATCH/DELETE)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.TeamSerializer

    def get_object(self):
        team = services.get_team_for_user(self.kwargs["pk"], self.request.user)
        if team is None:
            raise exceptions.NotFound("Équipe introuvable.")
        return team

    def partial_update(self, request, *args, **kwargs):
        team = self.get_object()
        serializer = serializers.CreateTeamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = services.update_team(team, request.user, serializer.validated_data["name"])
        except services.TeamsServiceError as exc:
            return _service_error(exc)
        output = serializers.TeamSerializer(updated, context={"request": request})
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        team = self.get_object()
        try:
            services.delete_team(team, request.user)
        except services.TeamsServiceError as exc:
            return _service_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _get_team_or_404(kwargs: dict, user):
    team = services.get_team_for_user(kwargs["team_id"], user)
    if team is None:
        raise exceptions.NotFound("Équipe introuvable.")
    return team


class MemberListView(generics.ListCreateAPIView):
    """Membres d'une équipe + invitation (propriétaire uniquement)."""

    permission_classes = [permissions.IsAuthenticated]
    # Pour drf-spectacular (inférence du modèle) ; remplacé par ``get_queryset``.
    queryset = TeamMembership.objects.none()
    serializer_class = serializers.TeamMembershipSerializer
    filterset_fields = ("role", "status")

    def get_queryset(self):
        team = _get_team_or_404(self.kwargs, self.request.user)
        return (
            TeamMembership.objects.filter(team=team)
            .exclude(status=TeamMembership.Status.REMOVED)
            .select_related("user")
        )

    def create(self, request, *args, **kwargs):
        team = _get_team_or_404(kwargs, request.user)
        serializer = serializers.InviteMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target = get_object_or_404(User, pk=data["user_id"])
        try:
            membership = services.add_member(
                team, target, actor=request.user, role=data["role"], request=request
            )
        except services.TeamsServiceError as exc:
            return _service_error(exc)
        output = serializers.TeamMembershipSerializer(membership, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class MemberDetailView(generics.DestroyAPIView):
    """Retrait d'un membre (propriétaire de l'équipe ou le membre lui-même)."""

    permission_classes = [permissions.IsAuthenticated]
    # Pour drf-spectacular (inférence du modèle) ; la réponse est un 204 sans corps.
    queryset = User.objects.none()
    serializer_class = serializers.TeamMembershipSerializer

    def destroy(self, request, *args, **kwargs):
        team = _get_team_or_404(kwargs, request.user)
        target = get_object_or_404(User, pk=kwargs["user_id"])
        try:
            services.remove_member(team, target, actor=request.user, request=request)
        except services.TeamsServiceError as exc:
            return _service_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AccessGrantListView(generics.ListCreateAPIView):
    """Grants que j'ai accordés + (en tant que coach) grants qui me sont adressés.

    La création est réservée au propriétaire du profil sportif concerné et
    exige un email vérifié (``IsEmailVerified``, feature 02).
    """

    permission_classes = [permissions.IsAuthenticated, IsEmailVerified]
    # Pour drf-spectacular (inférence du modèle) ; remplacé par ``get_queryset``.
    queryset = AccessGrant.objects.none()
    serializer_class = serializers.AccessGrantSerializer
    filterset_fields = ("status", "grantee_type")

    def get_queryset(self):
        return (
            AccessGrant.objects.filter(
                Q(granted_by=self.request.user) | Q(grantee_coach__user=self.request.user)
            )
            .distinct()
            .select_related("athlete", "grantee_coach", "grantee_team")
        )

    def create(self, request, *args, **kwargs):
        from apps.athletes.models import AthleteProfile

        serializer = serializers.CreateGrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        athlete = get_object_or_404(AthleteProfile, pk=data["athlete"])
        try:
            grant = services.grant_access(
                request.user,
                athlete,
                grantee_type=data["grantee_type"],
                grantee_id=data["grantee_id"],
                scope_list=data["scopes"],
                expires_at=data.get("expires_at"),
                request=request,
            )
        except services.TeamsServiceError as exc:
            return _service_error(exc)
        output = serializers.AccessGrantSerializer(grant, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class AccessGrantAcceptView(generics.GenericAPIView):
    """Le coach bénéficiaire accepte un grant ``pending`` (email vérifié requis)."""

    permission_classes = [permissions.IsAuthenticated, IsEmailVerified]
    serializer_class = serializers.AccessGrantSerializer

    def post(self, request, *args, **kwargs):
        try:
            grant = services.accept_grant(request.user, kwargs["pk"], request=request)
        except services.TeamsServiceError as exc:
            return _service_error(exc)
        output = serializers.AccessGrantSerializer(grant, context={"request": request})
        return Response(output.data)


class AccessGrantRevokeView(generics.GenericAPIView):
    """Le propriétaire du profil révoque un grant (effet immédiat)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.AccessGrantSerializer

    def post(self, request, *args, **kwargs):
        try:
            grant = services.revoke_grant(request.user, kwargs["pk"], request=request)
        except services.TeamsServiceError as exc:
            return _service_error(exc)
        output = serializers.AccessGrantSerializer(grant, context={"request": request})
        return Response(output.data)
