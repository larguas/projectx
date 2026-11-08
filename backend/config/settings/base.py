"""Réglages communs à tous les environnements.

Toute la configuration est lue depuis les variables d'environnement
(via django-environ, fichier `.env` optionnel dans `backend/`).
Aucun secret ne doit apparaître dans ce fichier.
"""

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
    "drf_spectacular",
    "django_filters",
]

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
    "EXCEPTION_HANDLER": "core.exceptions.drf_exception_handler",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "core.openapi.EMGAutoSchema",
}

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
