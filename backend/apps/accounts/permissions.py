"""Permissions de la feature 02 (accounts).

``IsEmailVerified`` est réutilisée par la suite (feature 03) : un utilisateur
non vérifié peut se connecter et utiliser son espace personnel, mais ne peut
pas accepter ni créer d'autorisation de partage ni demander d'export.
"""

from rest_framework.permissions import BasePermission


class IsEmailVerified(BasePermission):
    """Autorise uniquement les utilisateurs dont l'email est vérifié."""

    message = "Vérifiez votre adresse email avant d'utiliser cette fonctionnalité."

    def has_permission(self, request, view) -> bool:  # noqa: ARG002 - signature DRF
        user = request.user
        return bool(user and user.is_authenticated and user.email_verified_at is not None)
