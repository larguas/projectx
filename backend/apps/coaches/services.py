"""Couche de services de la feature 03 (app ``coaches``).

Le profil coach est créé À LA DEMANDE par l'utilisateur qui devient coach
(pas de nouveau compte : un utilisateur peut cumuler les rôles sportif et
coach). La mise à jour reste réservée au propriétaire du profil.

Les erreurs lèvent ``CoachesServiceError`` avec un code stable mappé en HTTP
par les vues (``conflict`` -> 409, ``forbidden`` -> 403).
"""

from __future__ import annotations


class CoachesServiceError(Exception):
    """Erreur métier des services coaches ; ``code`` est le code stable de l'API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def get_own_profile(user):
    """Profil coach de ``user`` ou ``None`` (pas encore créé)."""
    from apps.coaches.models import CoachProfile

    return CoachProfile.objects.filter(user=user).first()


def create_own_profile(user, data: dict):
    """Crée le profil coach de ``user`` ; ``conflict`` s'il existe déjà."""
    from apps.coaches.models import CoachProfile

    if CoachProfile.objects.filter(user=user).exists():
        raise CoachesServiceError("conflict", "Vous avez déjà un profil coach.")
    return CoachProfile.objects.create(user=user, **data)


def update_own_profile(user, profile, data: dict):
    """Met à jour le profil ; seul le propriétaire peut le faire."""
    if profile.user_id != user.pk:
        raise CoachesServiceError("forbidden", "Seul le propriétaire peut modifier ce profil.")
    for field, value in data.items():
        setattr(profile, field, value)
    profile.save()
    return profile
