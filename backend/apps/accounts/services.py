"""Couche de services de la feature 02 (accounts) : logique métier typée, sans HTTP.

Politique de mots de passe (documentée) :
- minimum 10 caractères,
- pas de mot de passe courant,
- pas uniquement numérique,
- suffisamment différent des attributs du compte (email, noms).

Elle est appliquée par les validateurs Django (``AUTH_PASSWORD_VALIDATORS``)
via ``validate_password_policy()``.

Jetons :
- Réinitialisation de mot de passe : jeton signé Django
  (``PasswordResetTokenGenerator``) à durée limitée (``PASSWORD_RESET_TIMEOUT``,
  1 h par défaut) ; il devient invalide dès que le mot de passe change
  (usage unique, sans état en base).
- Vérification d'email : jeton signé horodaté (``TimestampSigner``) dont la
  charge ne contient que des données non sensibles ; il est invalidé dès que
  l'adresse est vérifiée.

Flux « device code » : codes à usage unique, courte durée (5 minutes),
stockés hachés (SHA-256), polling borné (intervalle de 5 s, 100 tentatives).
"""

from __future__ import annotations

import binascii
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import signing
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import (
    DeviceAuthorization,
    User,
    generate_user_code,
    hash_code,
)

# --- Politique de mot de passe --------------------------------------------------------


def validate_password_policy(password: str, user: User | None = None) -> None:
    """Applique la politique de mots de passe ; lève ``ValidationError`` sinon."""
    validate_password(password, user=user)


# --- Vérification d'email ----------------------------------------------------------------

_verification_signer = signing.TimestampSigner(salt="accounts.email-verification")
EMAIL_VERIFICATION_MAX_AGE = timedelta(hours=24)


def generate_email_verification_token(user: User) -> str:
    """Jeton signé (horodaté) de vérification d'email.

    La charge ne contient que des données non sensibles (uuid + état de
    vérification) : une fois l'utilisateur vérifié, le jeton devient invalide
    (usage unique).
    """
    return _verification_signer.sign_object(
        {"uid": str(user.id), "verified": user.email_verified_at is not None}
    )


def consume_email_verification_token(token: str) -> User | None:
    """Valide un jeton de vérification ; retourne l'utilisateur non vérifié.

    Retourne ``None`` si le jeton est invalide, expiré, déjà utilisé, ou si le
    compte n'existe plus / a été vérifié entre-temps.
    """
    try:
        payload = _verification_signer.unsign_object(
            token, max_age=EMAIL_VERIFICATION_MAX_AGE.total_seconds()
        )
    except signing.SignatureExpired:
        return None
    except signing.BadSignature:
        return None
    user = User.objects.filter(id=payload.get("uid")).first()
    if user is None or user.email_verified_at is not None or payload.get("verified") is not False:
        return None
    return user


def send_email_verification_email(user: User) -> None:
    """Envoie l'email de vérification (backend console en dev, locmem en tests)."""
    token = generate_email_verification_token(user)
    link = f"{settings.FRONTEND_URL}/auth/email/verify?token={token}"
    EmailMessage(
        subject="Vérifiez votre adresse email — Plateforme EMG",
        body=(
            "Bonjour,\n\n"
            "Merci de vérifier votre adresse email en cliquant sur le lien ci-dessous "
            f"(valable {EMAIL_VERIFICATION_MAX_AGE.days} jour(s)) :\n\n"
            f"{link}\n\n"
            "Si vous n'avez pas créé de compte, ignorez cet email.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    ).send()


# --- Réinitialisation de mot de passe ------------------------------------------------------

_reset_token_generator = PasswordResetTokenGenerator()


def request_password_reset(email: str) -> bool:
    """Envoie un email de réinitialisation si le compte existe et est actif.

    Ne révèle jamais l'existence d'un compte (la réponse de l'endpoint est
    identique dans tous les cas). Retourne ``True`` si un email a été envoyé.
    """
    user = User.objects.filter(email=email.lower().strip()).first()
    if user is None or not user.is_active:
        return False
    token = _reset_token_generator.make_token(user)
    uidb64 = urlsafe_base64_encode(force_bytes(str(user.id)))
    link = f"{settings.FRONTEND_URL}/auth/password/reset?uid={uidb64}&token={token}"
    EmailMessage(
        subject="Réinitialisation de votre mot de passe — Plateforme EMG",
        body=(
            "Bonjour,\n\n"
            "Vous avez demandé la réinitialisation de votre mot de passe. Cliquez sur "
            f"le lien ci-dessous (valable {settings.PASSWORD_RESET_TIMEOUT // 60} minutes) :\n\n"
            f"{link}\n\n"
            "Si vous n'avez pas fait cette demande, ignorez cet email : votre mot de "
            "passe restera inchangé.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    ).send()
    return True


def reset_password(uid_b64: str, token: str, new_password: str) -> User | None:
    """Réinitialise le mot de passe avec un jeton signé valide et à usage unique.

    Retourne l'utilisateur en cas de succès ; ``None`` si le jeton est invalide,
    expiré ou déjà utilisé (le changement de mot de passe invalide les anciens
    jetons). Lève ``ValidationError`` si le nouveau mot de passe ne respecte pas
    la politique.
    """
    try:
        uid = urlsafe_base64_decode(uid_b64).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None
    user = User.objects.filter(id=uid).first()
    if user is None or not _reset_token_generator.check_token(user, token):
        return None
    validate_password_policy(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    return user


def change_password(user: User, new_password: str) -> None:
    """Change le mot de passe (l'ancien a été vérifié en amont).

    Invalide au passage les jetons de réinitialisation en cours (leur empreinte
    intègre le champ ``password``).
    """
    validate_password_policy(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password"])


# --- Autorisation du module PC / mobile (flux « device code ») -----------------------------


@dataclass(frozen=True)
class DeviceCodeIssuance:
    """Résultat d'une émission de codes : les codes bruts ne sont renvoyés qu'une fois."""

    authorization: DeviceAuthorization
    device_code: str
    user_code: str


def create_device_authorization(
    client_type: str, client_name: str = "", client_version: str = ""
) -> DeviceCodeIssuance:
    """Crée une autorisation ``pending`` et retourne les codes bruts (une seule fois).

    Les codes sont stockés hachés (SHA-256) : le ``device_code`` ne pourra plus
    être relu depuis la base, et le ``user_code`` n'est jamais lu.
    """
    device_code = secrets.token_urlsafe(32)
    user_code = generate_user_code()
    authorization = DeviceAuthorization.objects.create(
        device_code_hash=hash_code(device_code),
        user_code_hash=hash_code(user_code),
        client_type=client_type,
        client_name=client_name,
        client_version=client_version,
        expires_at=timezone.now() + DeviceAuthorization.CODE_TTL,
    )
    return DeviceCodeIssuance(
        authorization=authorization, device_code=device_code, user_code=user_code
    )


@dataclass(frozen=True)
class DevicePollResult:
    """Résultat d'une demande de jetons par le client.

    ``status`` : ``granted``, ``pending``, ``slow_down``, ``denied``,
    ``expired`` ou ``invalid_grant`` ; la paire JWT n'est présente que pour
    ``granted``.
    """

    status: str
    access_token: str | None = None
    refresh_token: str | None = None


def _issue_device_tokens(authorization: DeviceAuthorization) -> tuple[str, str]:
    """Paire JWT du flux device code, avec claims de révocabilité.

    Les jetons portent ``client_type`` et ``device_auth_id`` : le renouvellement
    (refresh) est refusé si l'autorisation a été révoquée entre-temps.
    """
    assert authorization.user is not None  # approuvée ⇒ utilisateur lié
    refresh = RefreshToken.for_user(authorization.user)
    refresh["client_type"] = authorization.client_type
    refresh["device_auth_id"] = str(authorization.id)
    access = refresh.access_token  # copie les claims (hors exp/jti/iat/token_type)
    return str(access), str(refresh)


def poll_device_token(device_code: str) -> DevicePollResult:
    """Demande de jetons du client (polling).

    - code inconnu ou déjà consommé → ``invalid_grant`` (usage unique) ;
    - code expiré, ou tentatives maximales atteintes → ``expired`` ;
    - polling trop rapide (< 5 s) → ``slow_down`` (non compté comme tentative) ;
    - approuvée → l'autorisation est consommée de façon atomique (verrou de
      ligne) et une paire JWT est émise.
    """
    now = timezone.now()
    authorization = DeviceAuthorization.objects.filter(
        device_code_hash=hash_code(device_code)
    ).first()
    if authorization is None or authorization.status == DeviceAuthorization.Status.CONSUMED:
        return DevicePollResult(status="invalid_grant")

    # Expiration au vol : une autorisation pending hors délai est clôturée.
    if (
        authorization.expires_at <= now
        and authorization.status == DeviceAuthorization.Status.PENDING
    ):
        DeviceAuthorization.objects.filter(
            pk=authorization.pk, status=DeviceAuthorization.Status.PENDING
        ).update(status=DeviceAuthorization.Status.EXPIRED)
        return DevicePollResult(status="expired")

    if authorization.status == DeviceAuthorization.Status.DENIED:
        return DevicePollResult(status="denied")
    if authorization.status == DeviceAuthorization.Status.EXPIRED:
        return DevicePollResult(status="expired")

    # Polling trop rapide : on demande d'attendre l'intervalle (non compté).
    if authorization.last_polled_at is not None and (
        now - authorization.last_polled_at
    ) < timedelta(seconds=DeviceAuthorization.POLL_INTERVAL_SECONDS):
        return DevicePollResult(status="slow_down")

    with transaction.atomic():
        # Verrou de ligne : deux pollings concurrents ne peuvent pas consommer
        # le même code (usage unique garanti).
        locked = DeviceAuthorization.objects.select_for_update().get(pk=authorization.pk)
        if locked.status == DeviceAuthorization.Status.APPROVED:
            access_token, refresh_token = _issue_device_tokens(locked)
            locked.status = DeviceAuthorization.Status.CONSUMED
            locked.last_polled_at = now
            locked.save(update_fields=["status", "last_polled_at", "updated_at"])
            return DevicePollResult(
                status="granted", access_token=access_token, refresh_token=refresh_token
            )
        if locked.status == DeviceAuthorization.Status.PENDING:
            locked.poll_attempts += 1
            locked.last_polled_at = now
            if locked.poll_attempts > DeviceAuthorization.MAX_POLL_ATTEMPTS:
                locked.status = DeviceAuthorization.Status.EXPIRED
            locked.save(update_fields=["status", "last_polled_at", "poll_attempts", "updated_at"])
            return DevicePollResult(
                status="expired"
                if locked.status == DeviceAuthorization.Status.EXPIRED
                else "pending"
            )
        # denied / expired (changés entre le premier lecture et le verrou).
        return DevicePollResult(
            status="denied" if locked.status == DeviceAuthorization.Status.DENIED else "expired"
        )


class DeviceFlowError(Exception):
    """État invalide du flux device code ; ``code`` est le code stable de l'API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def approve_device_authorization(user_code: str, user: User, approve: bool) -> DeviceAuthorization:
    """Approuve ou refuse une autorisation à partir du ``user_code`` saisi.

    Lève ``DeviceFlowError`` avec un code stable : ``invalid_request`` (code
    inconnu — réponse générique, sans révéler d'existence), ``expired_token``
    ou ``conflict`` (déjà approuvée / refusée / consommée).
    """
    now = timezone.now()
    normalized_code = user_code.strip().upper()
    authorization = DeviceAuthorization.objects.filter(
        user_code_hash=hash_code(normalized_code)
    ).first()
    if authorization is None:
        raise DeviceFlowError("invalid_request", "Code invalide.")

    if (
        authorization.expires_at <= now
        and authorization.status == DeviceAuthorization.Status.PENDING
    ):
        DeviceAuthorization.objects.filter(
            pk=authorization.pk, status=DeviceAuthorization.Status.PENDING
        ).update(status=DeviceAuthorization.Status.EXPIRED)
        raise DeviceFlowError("expired_token", "Ce code est expiré.")

    with transaction.atomic():
        locked = DeviceAuthorization.objects.select_for_update().get(pk=authorization.pk)
        if locked.expires_at <= now and locked.status == DeviceAuthorization.Status.PENDING:
            locked.status = DeviceAuthorization.Status.EXPIRED
            locked.save(update_fields=["status", "updated_at"])
            raise DeviceFlowError("expired_token", "Ce code est expiré.")
        if locked.status != DeviceAuthorization.Status.PENDING:
            raise DeviceFlowError("conflict", "Cette autorisation a déjà été traitée.")
        locked.status = (
            DeviceAuthorization.Status.APPROVED if approve else DeviceAuthorization.Status.DENIED
        )
        locked.user = user
        locked.save(update_fields=["status", "user", "updated_at"])
    return locked


def revoke_device_authorization(user: User, authorization_id: str) -> DeviceAuthorization | None:
    """Révoque un client (statut → ``denied``) ; ``None`` si introuvable / non propriétaire.

    Une autorisation consommée peut être révoquée : le client ne pourra plus
    renouveler ses jetons (vérification au refresh).
    """
    authorization = DeviceAuthorization.objects.filter(id=authorization_id, user=user).first()
    if authorization is None:
        return None
    if authorization.status != DeviceAuthorization.Status.DENIED:
        authorization.status = DeviceAuthorization.Status.DENIED
        authorization.save(update_fields=["status", "updated_at"])
    return authorization


def is_device_authorization_active(authorization_id: str) -> bool:
    """Le client peut-il (re)nouveler ses jetons ? (approuvée ou consommée, non révoquée)."""
    authorization = DeviceAuthorization.objects.filter(id=authorization_id).first()
    return authorization is not None and authorization.is_active_authorization
