from django.apps import AppConfig


class SessionsConfig(AppConfig):
    """Feature 06 : séances d'acquisition.

    ``label = "training_sessions"`` — le nom ``sessions`` entre en conflit avec
    ``django.contrib.sessions`` (décision n°2 de ``docs/00-index.md``) ; les FK
    inter-apps pointent donc vers ``"training_sessions.Session"``.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sessions"
    label = "training_sessions"
    verbose_name = "Séances d'acquisition"
