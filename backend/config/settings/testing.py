"""Réglages pour la suite de tests (pytest).

La base de données de test est PostgreSQL (pytest-django crée `test_<db>`).
Sentry est désactivé : aucun event ne doit partir pendant les tests.
"""

import os
import tempfile
from pathlib import Path

os.environ["DEBUG"] = "False"
os.environ["SENTRY_DSN"] = ""

from config.settings.base import *  # noqa: E402,F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True

# Emails captés en mémoire (django.core.mail.outbox) : aucun envoi réel.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Taux de throttling généreux par défaut ; les tests dédiés au throttling
# abaissent ces valeurs via la fixture ``settings`` (REST_FRAMEWORK entier).
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        scope: "1000/min" for scope in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    },  # noqa: F405
}

# Les photos de test vont dans un répertoire temporaire (pas dans le dépôt).
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="emg-test-media-"))  # noqa: F405
