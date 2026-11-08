"""Réglages de développement local (défaut via manage.py)."""

import os

# En développement : DEBUG activé par défaut, environnement Sentry "development".
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("SENTRY_ENVIRONMENT", "development")

from config.settings.base import *  # noqa: E402,F401,F403

ALLOWED_HOSTS = ["*"]
