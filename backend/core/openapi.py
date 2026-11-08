"""Extensions drf-spectacular : conventions de schéma (décision n°14).

``EMGAutoSchema`` injecte automatiquement ``ErrorResponse`` (format d'erreur
unique) dans les réponses de toutes les opérations, avec les codes gérés par
``core.exceptions.drf_exception_handler``. À brancher via
``REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"]``.
"""

from drf_spectacular.openapi import AutoSchema as BaseAutoSchema

# Statut HTTP -> description dans le schéma.
_ERROR_RESPONSES: dict[int, str] = {
    400: "Erreur de validation.",
    401: "Authentification requise ou jeton invalide.",
    403: "Accès refusé.",
    404: "Ressource introuvable.",
    409: "Conflit avec l'état actuel de la ressource.",
    500: "Erreur interne du serveur.",
}


class EMGAutoSchema(BaseAutoSchema):
    """AutoSchema avec réponses d'erreur typées sur toutes les opérations."""

    def _get_response_bodies(self, direction="response"):
        responses = super()._get_response_bodies(direction)

        from core.serializers import ErrorResponse

        component = self.resolve_serializer(ErrorResponse(), direction)
        if not component:
            return responses
        ref = component.ref

        for status_code, description in _ERROR_RESPONSES.items():
            responses.setdefault(
                str(status_code),
                {
                    "description": description,
                    "content": {"application/json": {"schema": ref}},
                },
            )
        return responses
