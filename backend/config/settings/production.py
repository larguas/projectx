"""Réglages de production : durcissement minimal.

Le déploiement complet (audit, RGPD, TLS) arrive avec la feature 14 ;
ici on garantit seulement qu'une config invalide échoue au démarrage.
"""

import os

os.environ["DEBUG"] = "False"
os.environ.setdefault("SENTRY_ENVIRONMENT", "production")

from django.core.exceptions import ImproperlyConfigured  # noqa: E402

from config.settings.base import *  # noqa: E402,F401,F403

if DEBUG:
    raise ImproperlyConfigured("DEBUG doit être False en production.")
if SECRET_KEY == "insecure-dev-key-change-me":
    raise ImproperlyConfigured("Définissez une valeur de SECRET_KEY dédiée à la production.")

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
