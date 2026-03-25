from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self) -> None:
        # Enregistre les triggers d'audit après chargement
        from . import signals

        signals.register_audit_triggers()

