from django.apps import AppConfig


class ManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "management"

    def ready(self) -> None:
        # Ensure drf-spectacular discovers custom OpenAPI extensions.
        from management.actions.registry import autodiscover

        autodiscover()

        from management import signals

        signals.connect_signals()
