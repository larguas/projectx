"""Réglages pour la suite de tests (pytest).

La base de données de test est PostgreSQL (pytest-django crée `test_<db>`).
Sentry est désactivé : aucun event ne doit partir pendant les tests.
"""

import os

os.environ["DEBUG"] = "False"
os.environ["SENTRY_DSN"] = ""

from config.settings.base import *  # noqa: E402,F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
