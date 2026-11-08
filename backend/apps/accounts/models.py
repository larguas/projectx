"""Modèles de la feature 02 : utilisateur et autorisation des clients (device code).

- ``User`` : utilisateur personnalisé, email comme identifiant unique.
- ``DeviceAuthorization`` : flux « device code » d'autorisation du module PC /
  mobile (décision d'architecture n°7) : un client de bureau obtient des JWT
  sans jamais transmettre le mot de passe de l'utilisateur.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from core.models import TimestampedModel, UUIDModel


class UserManager(BaseUserManager):
    """Gestionnaire ``User`` : l'email est l'identifiant (normalisé en minuscules)."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields) -> "User":
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superutilisateur doit avoir ``is_staff=True``.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superutilisateur doit avoir ``is_superuser=True``.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, UUIDModel):
    """Utilisateur de la plateforme : l'email est l'identifiant unique.

    Pas de champ ``role`` : un utilisateur peut cumuler des rôles (individuel,
    sportif, coach) portés par des profils dédiés en feature 03. Seul
    ``is_staff`` / superuser désigne un administrateur de la plateforme.
    """

    email = models.EmailField("adresse email", unique=True)
    first_name = models.CharField("prénom", max_length=150, blank=True)
    last_name = models.CharField("nom", max_length=150, blank=True)
    is_active = models.BooleanField(
        "actif",
        default=True,
        help_text="Les comptes inactifs ne peuvent pas se connecter ni créer de compte.",
    )
    is_staff = models.BooleanField(
        "personnel", default=False, help_text="Membre du personnel (accès admin)."
    )
    date_joined = models.DateTimeField("date d'inscription", auto_now_add=True)
    email_verified_at = models.DateTimeField("email vérifié le", null=True, blank=True)
    locale = models.CharField("locale", max_length=35, default="en")
    timezone = models.CharField("fuseau horaire (IANA)", max_length=60, default="UTC")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ("date_joined",)

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs) -> None:  # noqa: ARG002 - signature Django
        """Normalise l'email en minuscules avant toute écriture."""
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)


class DeviceAuthorization(TimestampedModel, UUIDModel):
    """Autorisation d'un client (module PC / mobile) via flux « device code ».

    Cycle de vie : ``pending`` → ``approved`` (saisie du ``user_code`` par
    l'utilisateur dans le navigateur), puis ``consumed`` après échange unique
    contre une paire JWT ; ou ``denied`` (refus/révocation) / ``expired``.

    Les deux codes sont stockés hachés (SHA-256) : le ``device_code`` n'est
    renvoyé qu'une fois, à la création ; le ``user_code`` est saisi par
    l'utilisateur et jamais lu depuis la base.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "En attente d'approbation"
        APPROVED = "approved", "Approuvé"
        DENIED = "denied", "Refusé ou révoqué"
        EXPIRED = "expired", "Expiré"
        CONSUMED = "consumed", "Échangé contre des jetons"

    class ClientType(models.TextChoices):
        PC_AGENT = "pc_agent", "Module PC"
        MOBILE = "mobile", "Mobile"

    # Paramètres du flux : codes à usage unique, courte durée, limitation de tentatives.
    CODE_TTL = timedelta(minutes=5)
    POLL_INTERVAL_SECONDS = 5
    MAX_POLL_ATTEMPTS = 100

    device_code_hash = models.CharField(
        "device_code (haché)", max_length=64, unique=True, editable=False
    )
    user_code_hash = models.CharField(
        "user_code (haché)", max_length=64, unique=True, editable=False
    )
    status = models.CharField(
        "statut", max_length=16, choices=Status.choices, default=Status.PENDING
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="utilisateur",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="device_authorizations",
    )
    client_type = models.CharField("type de client", max_length=16, choices=ClientType.choices)
    client_name = models.CharField("nom du client", max_length=200, blank=True)
    client_version = models.CharField("version du client", max_length=50, blank=True)
    expires_at = models.DateTimeField("expire le")
    last_polled_at = models.DateTimeField("dernier polling", null=True, blank=True)
    poll_attempts = models.PositiveIntegerField("tentatives de polling", default=0)

    class Meta:
        verbose_name = "autorisation de client"
        verbose_name_plural = "autorisations de clients"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.client_type} {self.pk} ({self.status})"

    @property
    def is_active_authorization(self) -> bool:
        """Le client peut-il (re)nouveler ses jetons ?"""
        return self.status in (self.Status.APPROVED, self.Status.CONSUMED)


def hash_code(value: str) -> str:
    """Empreinte SHA-256 hexadécimale d'un code (``device_code`` / ``user_code``)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# Alphabet sans caractères ambigus (pas de I, L, O, 0, 1) pour un code
# saisissable à la main.
_USER_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_user_code() -> str:
    """Génère un ``user_code`` court au format ``XXXX-XXXX``."""
    return "-".join(
        "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(4)) for _ in range(2)
    )
