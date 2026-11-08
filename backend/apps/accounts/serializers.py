"""Sérialiseurs de la feature 02 (accounts).

Les mots de passe sont validés par les validateurs Django (politique
documentée dans ``services.validate_password_policy``) ; les erreurs sont
renvoyées au format d'erreur unique via le handler global.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions, serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from apps.accounts.models import DeviceAuthorization, User
from apps.accounts.services import (
    is_device_authorization_active,
    send_email_verification_email,
    validate_password_policy,
)


def _invalid_refresh_token_error() -> exceptions.AuthenticationFailed:
    """401 identique pour tout jeton refresh invalide, expiré ou blacklisté."""
    return exceptions.AuthenticationFailed("Jeton refresh invalide ou expiré.")


class ClientRevokedError(exceptions.AuthenticationFailed):
    """Renouvellement refusé : l'autorisation device associée a été révoquée.

    Le handler global (``core.exceptions``) lit ``stable_code`` pour renvoyer
    le code stable ``client_revoked`` au lieu du 401 générique.
    """

    stable_code = "client_revoked"
    default_detail = "Ce client a été révoqué."


class UserSerializer(serializers.ModelSerializer):
    """Profil utilisateur (GET/PATCH ``/users/me/``)."""

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "date_joined",
            "email_verified_at",
            "locale",
            "timezone",
        )
        read_only_fields = ("id", "email", "is_active", "date_joined", "email_verified_at")


class RegisterSerializer(serializers.Serializer):
    """Inscription : email unique (insensible à la casse) + mot de passe politique."""

    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, min_length=10
    )
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)

    def validate_email(self, value: str) -> str:
        email = value.lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cette adresse email.")
        return email

    def validate_password(self, value: str) -> str:
        try:
            validate_password_policy(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def create(self, validated_data: dict) -> User:
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )
        send_email_verification_email(user)
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """Connexion par email (``USERNAME_FIELD``) : renvoie la paire access + refresh."""

    username_field = "email"

    def validate(self, attrs: dict) -> dict:
        # L'email est normalisé en minuscules (identifiant insensible à la casse).
        if self.username_field in attrs:
            attrs[self.username_field] = str(attrs[self.username_field]).lower()
        return super().validate(attrs)


class RefreshSerializer(TokenRefreshSerializer):
    """Renouvellement avec rotation : l'ancien refresh est blacklisté.

    Si le jeton porte le claim ``device_auth_id`` (flux device code), le client
    ne doit pas avoir été révoqué, sinon le renouvellement est refusé.
    """

    def validate(self, attrs: dict) -> dict:
        try:
            token = self.token_class(attrs["refresh"])
        except (TokenError, KeyError) as exc:
            # Jeton invalide / expiré / blacklisté (``KeyError`` : payload sans
            # ``jti``, levé par le blacklist avant la vérification du type) :
            # même 401 qu'un jeton inconnu.
            raise _invalid_refresh_token_error() from exc
        device_auth_id = token.payload.get("device_auth_id")
        if device_auth_id is not None and not is_device_authorization_active(device_auth_id):
            # Client révoqué : plus de renouvellement (critère d'acceptation).
            raise ClientRevokedError()
        try:
            return super().validate(attrs)
        except User.DoesNotExist as exc:
            # Compte supprimé après émission du jeton.
            raise _invalid_refresh_token_error() from exc


class LogoutSerializer(serializers.Serializer):
    """Déconnexion : blacklist du refresh token transmis."""

    refresh = serializers.CharField()

    def validate_refresh(self, value: str) -> str:
        try:
            self.token = RefreshToken(value)
        except (TokenError, KeyError) as exc:
            # Jeton invalide / expiré / blacklisté : 401 (cf. RefreshSerializer).
            raise _invalid_refresh_token_error() from exc
        return value

    def save(self, **kwargs):
        self.token.blacklist()


class PasswordForgotSerializer(serializers.Serializer):
    """Demande de réinitialisation : ne révèle jamais l'existence du compte."""

    email = serializers.EmailField()


class PasswordResetSerializer(serializers.Serializer):
    """Réinitialisation avec le jeton signé reçu par email (usage unique)."""

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, min_length=10
    )

    def validate_new_password(self, value: str) -> str:
        try:
            validate_password_policy(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class PasswordChangeSerializer(serializers.Serializer):
    """Changement de mot de passe (utilisateur authentifié)."""

    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, min_length=10
    )

    def validate_old_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate_new_password(self, value: str) -> str:
        try:
            validate_password_policy(value, user=self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class EmailVerifySerializer(serializers.Serializer):
    """Vérification d'email avec le jeton signé reçu par email."""

    token = serializers.CharField()


class EmailResendSerializer(serializers.Serializer):
    """Renvoi de l'email de vérification (throttlé)."""

    email = serializers.EmailField()


class DeviceCodeRequestSerializer(serializers.Serializer):
    """Demande d'un code d'autorisation pour un client de bureau / mobile."""

    client_type = serializers.ChoiceField(choices=DeviceAuthorization.ClientType.choices)
    client_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    client_version = serializers.CharField(required=False, allow_blank=True, max_length=50)


class DeviceCodeResponseSerializer(serializers.Serializer):
    """Codes d'autorisation : ``device_code`` n'est renvoyé qu'une seule fois."""

    device_code = serializers.CharField()
    user_code = serializers.CharField()
    verification_uri = serializers.CharField()
    expires_in = serializers.IntegerField()
    interval = serializers.IntegerField()


class DeviceTokenRequestSerializer(serializers.Serializer):
    """Demande de jetons du client (polling avec le ``device_code``)."""

    device_code = serializers.CharField()


class TokenPairSerializer(serializers.Serializer):
    """Paire JWT (access + refresh)."""

    access = serializers.CharField()
    refresh = serializers.CharField()


class MessageResponse(serializers.Serializer):
    """Réponse générique à un seul message (ne révèle jamais l'existence d'un compte)."""

    message = serializers.CharField()


class DeviceApproveSerializer(serializers.Serializer):
    """Approbation / refus d'une autorisation par l'utilisateur connecté."""

    user_code = serializers.CharField(max_length=16)
    approve = serializers.BooleanField()


class DeviceApproveResponse(serializers.Serializer):
    """Nouvel état de l'autorisation après approbation / refus."""

    status = serializers.ChoiceField(choices=["approved", "denied"])


class DeviceAuthorizationSerializer(serializers.ModelSerializer):
    """Client autorisé (module PC / mobile), pour la liste et la révocation."""

    class Meta:
        model = DeviceAuthorization
        fields = (
            "id",
            "client_type",
            "client_name",
            "client_version",
            "status",
            "created_at",
            "expires_at",
            "last_polled_at",
        )
        read_only_fields = fields
