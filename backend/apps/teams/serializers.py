"""Sérialiseurs de la feature 03 (app ``teams`` : équipes, membres, grants)."""

from rest_framework import serializers

from apps.teams.models import AccessGrant, Team, TeamMembership


class TeamSerializer(serializers.ModelSerializer):
    """Équipe (vue par ses membres)."""

    owner_email = serializers.EmailField(source="owner.email", read_only=True)

    class Meta:
        model = Team
        fields = ("id", "name", "owner_id", "owner_email", "created_at", "updated_at")
        read_only_fields = ("id", "owner_id", "created_at", "updated_at")


class CreateTeamSerializer(serializers.Serializer):
    """Création d'une équipe ; l'utilisateur devient propriétaire."""

    name = serializers.CharField(min_length=2, max_length=200)


class TeamMembershipSerializer(serializers.ModelSerializer):
    """Membre d'une équipe (l'email est visible par les co-équipiers)."""

    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = TeamMembership
        fields = ("id", "user_id", "email", "role", "status", "created_at")
        read_only_fields = fields


class InviteMemberSerializer(serializers.Serializer):
    """Invitation d'un membre par le propriétaire (rôle coach ou athlete)."""

    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(
        choices=[
            TeamMembership.Role.COACH,
            TeamMembership.Role.ATHLETE,
        ]
    )


class AccessGrantSerializer(serializers.ModelSerializer):
    """Autorisation de partage (vue côté sportif et côté coach bénéficiaire)."""

    grantee_coach_id = serializers.UUIDField(read_only=True)
    grantee_team_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = AccessGrant
        fields = (
            "id",
            "athlete_id",
            "granted_by_id",
            "grantee_type",
            "grantee_coach_id",
            "grantee_team_id",
            "scopes",
            "status",
            "granted_at",
            "revoked_at",
            "expires_at",
            "created_at",
        )
        read_only_fields = fields


class CreateGrantSerializer(serializers.Serializer):
    """Création d'un grant par le propriétaire du profil sportif.

    ``scopes`` : liste non vide de scopes connus (``core.scopes``) ; les
    inconnus sont refusés. ``grantee_id`` : identifiant du coach ou de l'équipe
    selon ``grantee_type``.
    """

    athlete = serializers.UUIDField()
    grantee_type = serializers.ChoiceField(choices=AccessGrant.GranteeType.choices)
    grantee_id = serializers.UUIDField()
    scopes = serializers.ListField(child=serializers.CharField(), min_length=1, allow_empty=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
