"""Permissions transverses de la plateforme (feature 03).

``HasAthleteScope`` est la classe de permission réutilisable par toutes les
apps : elle délègue la décision au module central ``core.access`` (jamais de
logique d'autorisation en double dans une vue).
"""

from rest_framework.permissions import BasePermission

from core import access


class HasAthleteScope(BasePermission):
    """Autorise l'accès à un objet si l'utilisateur porte le scope sur son sportif.

    La classe est paramétrée par le scope exigé::

        class SessionDetailView(generics.RetrieveAPIView):
            permission_classes = [IsAuthenticated, HasAthleteScope("sessions:read")]

    Règles :
    - ``has_permission`` exige seulement l'authentification (le filtrage des
      listes est fait dans ``get_queryset`` via ``core.access.visible_athletes``) ;
    - ``has_object_permission`` résout le sportif de l'objet : un objet qui est
      lui-même un ``AthleteProfile``, ou tout objet exposant un champ/attribut
      ``athlete`` (ex. une future ``Session``). C'est ce qui rend la classe
      réutilisable par toutes les features suivantes ;
    - le refus lève ``PermissionDenied`` (403) via DRF.

    Exemple::

        HasAthleteScope("analytics:read")  # sur un objet ayant ``.athlete``
    """

    message = "Accès non autorisé aux données de ce sportif."

    def __init__(self, scope: str) -> None:
        self.scope = scope

    def has_permission(self, request, view) -> bool:  # noqa: ARG002 - signature DRF
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:  # noqa: ARG002 - signature DRF
        athlete = getattr(obj, "athlete", None) or obj
        return access.can_access_athlete(request.user, athlete, self.scope)
