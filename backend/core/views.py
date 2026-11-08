"""Vues transverses de l'API (santé du service)."""

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core import health
from core.serializers import HealthResponse


class HealthView(APIView):
    """État de l'application, de la base de données et de Redis.

    200 si tous les checks sont OK, sinon 503 avec ``status: degraded``.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="health_check",
        responses={
            status.HTTP_200_OK: HealthResponse,
            status.HTTP_503_SERVICE_UNAVAILABLE: HealthResponse,
        },
    )
    def get(self, request):
        checks = health.run_checks()
        ok = all(value == "ok" for value in checks.values())
        return Response(
            {"status": "ok" if ok else "degraded", "checks": checks},
            status=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
