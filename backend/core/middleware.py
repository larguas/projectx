"""Middleware : identifiant de requête (``X-Request-ID``).

L'identifiant est propagé dans les logs structurés (contextvars structlog)
et renvoyé en réponse. S'il est absent de la requête, un UUID est généré.
"""

import uuid

import structlog


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        # Reset puis bind : les threads sont réutilisés par le serveur.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response
