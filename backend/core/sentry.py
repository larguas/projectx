"""Intégration Sentry : initialisation et nettoyage des champs sensibles.

Sentry est désactivé quand ``SENTRY_DSN`` est vide (dev local, tests).
Le ``before_send`` masque systématiquement les valeurs sensibles avant
envoi : mots de passe, jetons, en-têtes d'autorisation, ``samples``.
"""

import sentry_sdk

# Sous-chaînes (minuscules) : si une clé d'event en contient une, sa valeur est masquée.
# On cherche par sous-chaîne pour rester prudent (ex. ``user_password``, ``refresh_token``).
SENSITIVE_KEY_PATTERNS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "samples",
)

FILTERED_VALUE = "[FILTERED]"


def _scrub(value):
    if isinstance(value, dict):
        return {
            key: (
                FILTERED_VALUE
                if any(pattern in str(key).lower() for pattern in SENSITIVE_KEY_PATTERNS)
                else _scrub(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def scrub_event(event: dict | None) -> dict | None:
    """``before_send`` : masque les champs sensibles d'un event Sentry."""
    if event is None:
        return None
    return _scrub(event)


def init_sentry(
    dsn: str, traces_sample_rate: float = 0.1, environment: str = "development"
) -> None:
    """Initialise Sentry ; sans-op si la DSN est vide."""
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        before_send=scrub_event,
        send_default_pii=False,
    )
