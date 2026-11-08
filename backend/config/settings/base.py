"""Réglages communs à tous les environnements.

Toute la configuration est lue depuis les variables d'environnement
(via django-environ, fichier `.env` optionnel dans `backend/`).
Aucun secret ne doit apparaître dans ce fichier.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    env.read_env(str(_env_file))

# --- Django -----------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Tierces.
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    # Locales.
    "apps.accounts",
    "apps.athletes",
    "apps.coaches",
    "apps.teams",
    "apps.audit",
]

# Utilisateur personnalisé : email comme identifiant (feature 02).
AUTH_USER_MODEL = "accounts.User"

# Politique de mots de passe (documentée dans apps/accounts/services.py) :
# minimum 10 caractères, pas de mot de passe courant, pas uniquement
# numérique, et suffisamment différent des attributs du compte (email, noms).
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Durée de validité du jeton signé de réinitialisation de mot de passe
# (1 h par défaut ; le jeton devient caduc dès que le mot de passe change).
# En secondes (Django attend un entier, pas un timedelta).
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT_SECONDS", default=3600)

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Doit précéder les middlewares qui loggent pour que request_id soit présent.
    "core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Base de données (PostgreSQL, psycopg 3) --------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://emg:emg@localhost:5432/emg"),
}

# --- Redis / Celery -----------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True

# --- Observabilité --------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", default="development")
SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1)

# --- API ------------------------------------------------------------------------
DEFAULT_PAGE_SIZE = env.int("DEFAULT_PAGE_SIZE", default=50)
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Django REST Framework ---------------------------------------------------------
REST_FRAMEWORK = {
    # Deny by default : chaque vue déclare explicitement ses permissions.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # Le JWT est branché dès le socle ; les endpoints publics déclarent
    # ``authentication_classes = []`` et ``permission_classes = [AllowAny]``.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultPagination",
    "PAGE_SIZE": DEFAULT_PAGE_SIZE,
    # Le throttling s'active via les ``throttle_scope`` déclarés par vue
    # (ScopedRateThrottle laisse passer les vues sans scope).
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "EXCEPTION_HANDLER": "core.exceptions.drf_exception_handler",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "core.openapi.EMGAutoSchema",
    # Taux par scope (DRF lit ``DEFAULT_THROTTLE_RATES``) ; ajustable par
    # environnement.
    "DEFAULT_THROTTLE_RATES": {
        "login": env("THROTTLE_LOGIN", default="10/min"),
        "password_reset": env("THROTTLE_PASSWORD_RESET", default="5/min"),
        "email_resend": env("THROTTLE_EMAIL_RESEND", default="3/min"),
        "device_code": env("THROTTLE_DEVICE_CODE", default="5/min"),
        "device_approve": env("THROTTLE_DEVICE_APPROVE", default="10/min"),
    },
}

# --- JWT (feature 02 : simplejwt) -------------------------------------------------------
# Access court (5 min par défaut) ; refresh avec rotation + blacklist du jeton précédent.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=5)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# --- Email ---------------------------------------------------------------------------------
# En dev : backend console (les emails s'affichent dans le terminal).
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@emg.local")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)

# URL de l'application web (liens des emails et du flux device code).
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")

# --- drf-spectacular (contrat OpenAPI versionné, décision n°14) ----------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "API Plateforme EMG",
    "DESCRIPTION": "API de la plateforme de suivi musculaire et de performance sportive.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "COMPONENT_SPLIT_REQUEST": True,
    # Un seul nom d'enum pour les choix ["ok", "error"] du health (app/database/redis).
    "ENUM_NAME_OVERRIDES": {
        "HealthCheckState": ["ok", "error"],
    },
}

# --- Observabilité : logs structurés + Sentry (toutes les variables prêtes) ----------
from core.logging_config import configure_logging  # noqa: E402
from core.sentry import init_sentry  # noqa: E402

configure_logging(debug=DEBUG, level=LOG_LEVEL)
init_sentry(
    dsn=SENTRY_DSN,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    environment=SENTRY_ENVIRONMENT,
)
