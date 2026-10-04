from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "modules.accounts"
    label = "accounts"

    def ready(self):
        # Auth audit receivers (login success/failure). Imported here so they
        # are connected exactly once, after the app registry is populated.
        from . import signals  # noqa: F401
