"""Vues de la feature 02 (accounts) : inscription, auth JWT, profil, device code.

Conventions :
- Deny by default : chaque vue déclare explicitement ``permission_classes`` ;
  les endpoints publics ajoutent ``authentication_classes = []`` + ``AllowAny``.
- Format d'erreur unique via ``core.exceptions.error_response`` (codes stables).
"""

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts import services
from apps.accounts.models import DeviceAuthorization, User
from apps.accounts.serializers import (
    DeviceApproveResponse,
    DeviceApproveSerializer,
    DeviceAuthorizationSerializer,
    DeviceCodeRequestSerializer,
    DeviceCodeResponseSerializer,
    DeviceTokenRequestSerializer,
    EmailResendSerializer,
    EmailVerifySerializer,
    LoginSerializer,
    LogoutSerializer,
    MessageResponse,
    PasswordChangeSerializer,
    PasswordForgotSerializer,
    PasswordResetSerializer,
    RefreshSerializer,
    RegisterSerializer,
    TokenPairSerializer,
    UserSerializer,
)
from core.exceptions import error_response

# --- Inscription -----------------------------------------------------------------


class RegisterView(APIView):
    """Inscription (publique) : crée le compte et envoie l'email de vérification."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_register",
        request=RegisterSerializer,
        responses={status.HTTP_201_CREATED: UserSerializer},
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


# --- Connexion / renouvellement / déconnexion ---------------------------------------


class LoginView(TokenObtainPairView):
    """Connexion par email + mot de passe (throttlé) : paire access + refresh."""

    serializer_class = LoginSerializer
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_scope = "login"

    @extend_schema(
        operation_id="auth_login",
        request=LoginSerializer,
        responses={status.HTTP_200_OK: TokenPairSerializer},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class RefreshView(TokenRefreshView):
    """Renouvellement avec rotation (l'ancien refresh est blacklisté).

    Un client device code révoqué se voit refuser le renouvellement (401).
    """

    serializer_class = RefreshSerializer
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_refresh",
        request=RefreshSerializer,
        responses={status.HTTP_200_OK: TokenPairSerializer},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    """Déconnexion (authentifié) : blacklist du refresh token transmis."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="auth_logout",
        request=LogoutSerializer,
        responses={status.HTTP_204_NO_CONTENT: None},
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Mots de passe -------------------------------------------------------------------


class PasswordForgotView(APIView):
    """Demande de réinitialisation (publique, throttlé).

    La réponse est identique que le compte existe ou non.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_scope = "password_reset"

    @extend_schema(
        operation_id="auth_password_forgot",
        request=PasswordForgotSerializer,
        responses={status.HTTP_200_OK: MessageResponse},
    )
    def post(self, request):
        serializer = PasswordForgotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response(
            {
                "message": (
                    "Si un compte existe avec cette adresse, un email de "
                    "réinitialisation a été envoyé."
                )
            }
        )


class PasswordResetView(APIView):
    """Réinitialisation avec le jeton signé reçu par email (usage unique)."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_password_reset",
        request=PasswordResetSerializer,
        responses={status.HTTP_200_OK: MessageResponse},
    )
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = services.reset_password(
            uid_b64=data["uid"], token=data["token"], new_password=data["new_password"]
        )
        if user is None:
            return error_response(
                status.HTTP_400_BAD_REQUEST,
                code="invalid_reset_token",
                message="Lien de réinitialisation invalide ou expiré.",
            )
        return Response({"message": "Mot de passe réinitialisé avec succès."})


class PasswordChangeView(APIView):
    """Changement de mot de passe (authentifié) : vérifie l'ancien mot de passe."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="auth_password_change",
        request=PasswordChangeSerializer,
        responses={status.HTTP_200_OK: MessageResponse},
    )
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        services.change_password(request.user, serializer.validated_data["new_password"])
        return Response({"message": "Mot de passe modifié."})


# --- Profil ----------------------------------------------------------------------------


class MeView(generics.RetrieveUpdateAPIView):
    """Profil de l'utilisateur authentifié (GET / PATCH)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self) -> User:
        return self.request.user

    @extend_schema(
        operation_id="users_me",
        responses={status.HTTP_200_OK: UserSerializer},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="users_me_update",
        request=UserSerializer,
        responses={status.HTTP_200_OK: UserSerializer},
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(exclude=True)
    def put(self, request, *args, **kwargs):
        # Seul le PATCH est documenté (spécification) ; PUT -> 405.
        raise exceptions.MethodNotAllowed("PUT")


# --- Vérification d'email ----------------------------------------------------------------


class EmailVerifyView(APIView):
    """Vérification de l'adresse email avec le jeton signé (usage unique)."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_email_verify",
        request=EmailVerifySerializer,
        responses={status.HTTP_200_OK: MessageResponse},
    )
    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.consume_email_verification_token(serializer.validated_data["token"])
        if user is None:
            return error_response(
                status.HTTP_400_BAD_REQUEST,
                code="invalid_verification_token",
                message="Lien de vérification invalide ou expiré.",
            )
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
        return Response({"message": "Adresse email vérifiée."})


class EmailResendView(APIView):
    """Renvoi de l'email de vérification (publique, throttlé).

    La réponse est identique que le compte existe ou non.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_scope = "email_resend"

    @extend_schema(
        operation_id="auth_email_resend",
        request=EmailResendSerializer,
        responses={status.HTTP_200_OK: MessageResponse},
    )
    def post(self, request):
        serializer = EmailResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        user = User.objects.filter(email=email).first()
        if user is not None and user.email_verified_at is None:
            services.send_email_verification_email(user)
        return Response(
            {
                "message": (
                    "Si un compte non vérifié existe avec cette adresse, un email "
                    "de vérification a été envoyé."
                )
            }
        )


# --- Autorisation du module PC / mobile (flux « device code ») ---------------------------


class DeviceCodeView(APIView):
    """Émission d'un code d'autorisation (publique, throttlé).

    Le ``device_code`` est renvoyé une seule fois : il n'est stocké que haché.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_scope = "device_code"

    @extend_schema(
        operation_id="auth_device_code",
        request=DeviceCodeRequestSerializer,
        responses={status.HTTP_201_CREATED: DeviceCodeResponseSerializer},
    )
    def post(self, request):
        serializer = DeviceCodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        issuance = services.create_device_authorization(
            client_type=data["client_type"],
            client_name=data.get("client_name", ""),
            client_version=data.get("client_version", ""),
        )
        response = DeviceCodeResponseSerializer(
            {
                "device_code": issuance.device_code,
                "user_code": issuance.user_code,
                "verification_uri": (
                    f"{settings.FRONTEND_URL}/auth/device?user_code={issuance.user_code}"
                ),
                "expires_in": int(DeviceAuthorization.CODE_TTL.total_seconds()),
                "interval": DeviceAuthorization.POLL_INTERVAL_SECONDS,
            }
        )
        return Response(response.data, status=status.HTTP_201_CREATED)


class DeviceTokenView(APIView):
    """Demande de jetons du client (polling avec le ``device_code``).

    Codes d'erreur stables (HTTP 400) : ``authorization_pending``, ``slow_down``,
    ``access_denied``, ``expired_token``, ``invalid_grant`` ; sinon une paire JWT.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    _ERROR_STATUSES: dict[str, tuple[int, str, str]] = {
        "pending": (
            status.HTTP_400_BAD_REQUEST,
            "authorization_pending",
            "Autorisation en attente.",
        ),
        "slow_down": (
            status.HTTP_400_BAD_REQUEST,
            "slow_down",
            "Polling trop rapide, attendez l'intervalle.",
        ),
        "denied": (status.HTTP_400_BAD_REQUEST, "access_denied", "Autorisation refusée."),
        "expired": (status.HTTP_400_BAD_REQUEST, "expired_token", "Code expiré."),
        "invalid_grant": (
            status.HTTP_400_BAD_REQUEST,
            "invalid_grant",
            "Code device inconnu ou déjà utilisé.",
        ),
    }

    @extend_schema(
        operation_id="auth_device_token",
        request=DeviceTokenRequestSerializer,
        responses={status.HTTP_200_OK: TokenPairSerializer},
    )
    def post(self, request):
        serializer = DeviceTokenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.poll_device_token(serializer.validated_data["device_code"])
        if result.status == "granted":
            return Response({"access": result.access_token, "refresh": result.refresh_token})
        http_status, code, message = self._ERROR_STATUSES[result.status]
        return error_response(http_status, code=code, message=message)


class DeviceApproveView(APIView):
    """Approbation / refus d'une autorisation (utilisateur connecté, throttlé)."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "device_approve"

    @extend_schema(
        operation_id="auth_device_approve",
        request=DeviceApproveSerializer,
        responses={status.HTTP_200_OK: DeviceApproveResponse},
    )
    def post(self, request):
        serializer = DeviceApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            authorization = services.approve_device_authorization(
                user_code=data["user_code"], user=request.user, approve=data["approve"]
            )
        except services.DeviceFlowError as exc:
            if exc.code == "conflict":
                return error_response(status.HTTP_409_CONFLICT, code=exc.code, message=exc.message)
            return error_response(status.HTTP_400_BAD_REQUEST, code=exc.code, message=exc.message)
        return Response({"status": authorization.status})


class DeviceClientListView(generics.ListAPIView):
    """Clients autorisés (module PC / mobile) de l'utilisateur connecté."""

    permission_classes = [permissions.IsAuthenticated]
    # Pour drf-spectacular (inférence du modèle) ; remplacé par ``get_queryset``.
    queryset = DeviceAuthorization.objects.none()
    serializer_class = DeviceAuthorizationSerializer

    def get_queryset(self):
        return DeviceAuthorization.objects.filter(user=self.request.user).order_by("-created_at")

    @extend_schema(
        operation_id="auth_clients_list",
        responses={status.HTTP_200_OK: DeviceAuthorizationSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class DeviceClientDetailView(APIView):
    """Révocation d'un client (statut → ``denied``) : plus de refresh possible."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="auth_clients_revoke",
        responses={status.HTTP_204_NO_CONTENT: None},
    )
    def delete(self, request, authorization_id):
        authorization = services.revoke_device_authorization(request.user, authorization_id)
        if authorization is None:
            raise exceptions.NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)
