"""Sérialiseurs de la feature 03 (app ``coaches``).

Le profil coach est une identité professionnelle : l'annuaire
(``GET /api/v1/coaches/``) le rend consultable par tout utilisateur
authentifié afin qu'un sportif puisse choisir à qui accorder l'accès. L'email
n'est jamais exposé (donnée personnelle).
"""

from rest_framework import serializers

from apps.coaches.models import CoachProfile


class CoachProfileSerializer(serializers.ModelSerializer):
    """Profil coach (annuaire + détail)."""

    class Meta:
        model = CoachProfile
        fields = ("id", "organization_name", "bio", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class CreateCoachSerializer(serializers.Serializer):
    """Création à la demande du profil coach de l'utilisateur connecté."""

    organization_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    bio = serializers.CharField(required=False, allow_blank=True)
