from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Feature 02 : comptes, authentification JWT et autorisation du module PC."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Comptes"
