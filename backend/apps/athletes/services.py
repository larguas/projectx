"""Couche de services de la feature 03 (app ``athletes``).

Le profil sportif est créé À LA DEMANDE (pas à l'inscription) :
``create_own_profile`` est appelé par ``POST /api/v1/athletes/``. La mise à
jour reste réservée au propriétaire du profil — les grants n'autorisent que la
lecture des données métier, pas la modification du profil.

Les erreurs lèvent ``AthletesServiceError`` avec un code stable mappé en HTTP
par les vues (``conflict`` -> 409, ``forbidden`` -> 403).
"""

from __future__ import annotations


class AthletesServiceError(Exception):
    """Erreur métier des services athletes ; ``code`` est le code stable de l'API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def get_own_profile(user):
    """Profil sportif de ``user`` ou ``None`` (pas encore créé)."""
    from apps.athletes.models import AthleteProfile

    return AthleteProfile.objects.filter(user=user).first()


def create_own_profile(user, data: dict):
    """Crée le profil sportif de ``user`` ; ``conflict`` s'il existe déjà."""
    from apps.athletes.models import AthleteProfile

    if AthleteProfile.objects.filter(user=user).exists():
        raise AthletesServiceError("conflict", "Vous avez déjà un profil sportif.")
    return AthleteProfile.objects.create(user=user, **data)


def update_own_profile(user, profile, data: dict):
    """Met à jour le profil ; seul le propriétaire peut le faire."""
    if profile.user_id != user.pk:
        raise AthletesServiceError("forbidden", "Seul le propriétaire peut modifier ce profil.")
    for field, value in data.items():
        setattr(profile, field, value)
    profile.save()
    return profile
