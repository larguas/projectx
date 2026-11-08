"""Aides aux tests de la feature 02 (accounts)."""

import json
import re
from urllib.parse import parse_qs, urlparse

from rest_framework_simplejwt.tokens import RefreshToken


def post_json(client, url: str, payload: dict, **extra):
    """POST JSON via le client de test Django (``**extra`` : en-têtes HTTP)."""
    return client.post(url, data=json.dumps(payload), content_type="application/json", **extra)


def auth_headers(user) -> dict:
    """En-têtes HTTP avec un access token Bearer valide pour ``user``."""
    refresh = RefreshToken.for_user(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {refresh.access_token}"}


def login_tokens(client, email: str, password: str) -> tuple[str, str]:
    """Connexion via l'API ; retourne ``(access, refresh)``."""
    response = client.post(
        "/api/v1/auth/login/", {"email": email, "password": password}, format="json"
    )
    assert response.status_code == 200, response.data
    return response.data["access"], response.data["refresh"]


def token_from_link(body: str) -> dict[str, str]:
    """Extrait les paramètres de la première URL trouvée dans un corps d'email."""
    match = re.search(r"https?://\S+", body)
    assert match is not None, "Aucun lien trouvé dans l'email"
    query = parse_qs(urlparse(match.group(0)).query)
    return {key: value[0] for key, value in query.items()}


def last_email_body() -> str:
    """Corps du dernier email capté (backend locmem en tests)."""
    from django.core import mail

    assert mail.outbox, "Aucun email envoyé"
    return mail.outbox[-1].body
