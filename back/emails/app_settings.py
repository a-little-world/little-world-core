from pathlib import Path

from django.conf import settings


DEFAULT_EMAILS_CONFIG_PATH = Path(__file__).resolve().parent / "emails.json"


class EmailsAppSettings:
    @property
    def config_path(self) -> Path:
        app_settings = getattr(settings, "EMAILS_APP", {}) or {}
        configured_path = app_settings.get("CONFIG_PATH", getattr(settings, "EMAILS_CONFIG_PATH", DEFAULT_EMAILS_CONFIG_PATH))
        config_path = Path(configured_path)
        if not config_path.is_absolute():
            config_path = Path(settings.BASE_DIR) / config_path
        return config_path


emails_settings = EmailsAppSettings()
