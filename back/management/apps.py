from django.apps import AppConfig


class ManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "management"

    def ready(self) -> None:
        # Import all action handlers to populate the registry
        import admin_tasks.actions.change_profile_value  # noqa: F401
        import admin_tasks.actions.change_user_type  # noqa: F401
        import admin_tasks.actions.profile_review  # noqa: F401
        import admin_tasks.actions.remove_match  # noqa: F401
        import admin_tasks.actions.support_reply  # noqa: F401

        # Connect model signals
        from admin_tasks.signals import connect_signals

        connect_signals()
