"""Sérialiseurs transverses : réponses du health et contrat d'erreur unique.

Ces sérialiseurs servent aussi de référence pour le schéma OpenAPI
(décision n°14) : ``ErrorResponse`` est injecté sur toutes les opérations
par ``core.openapi.EMGAutoSchema``.
"""

from rest_framework import serializers


class CheckStatus(serializers.Serializer):
    app = serializers.ChoiceField(choices=["ok", "error"])
    database = serializers.ChoiceField(choices=["ok", "error"])
    redis = serializers.ChoiceField(choices=["ok", "error"])


class HealthResponse(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "degraded"])
    checks = CheckStatus()


class ErrorPayload(serializers.Serializer):
    code = serializers.CharField(help_text="Code d'erreur stable, machine-readable.")
    message = serializers.CharField()
    details = serializers.JSONField(
        required=False,
        allow_null=True,
        help_text="Détails (ex. erreurs par champ) ; null sinon.",
    )


class ErrorResponse(serializers.Serializer):
    error = ErrorPayload()
