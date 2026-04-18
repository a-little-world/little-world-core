from pathlib import Path

from django.conf import settings
from django.utils.module_loading import import_string

DEFAULT_EMAILS_CONFIG_PATH = Path(__file__).resolve().parent / "emails.json"

# Defaults for "normal authenticated user" endpoints (currently unused by the
# emails app itself, but exposed for projects that want to add user-facing
# email endpoints in the future, e.g. user-managed templates / preferences).
DEFAULT_API_AUTHENTICATION_CLASSES = [
    "rest_framework.authentication.SessionAuthentication",
]
DEFAULT_API_PERMISSION_CLASSES = [
    "rest_framework.permissions.IsAuthenticated",
]

# Defaults for "management user / admin" endpoints (template management,
# sending emails, dynamic templates, dev tooling, ...).  These endpoints are
# always considered admin-only inside the host project.  We default to
# `IsAdminUser` so a fresh integration is safe out of the box - any project
# that wants to broaden this (e.g. allow non-staff "matching" users) MUST
# explicitly override `ADMIN_API_PERMISSION_CLASSES`.
DEFAULT_ADMIN_API_AUTHENTICATION_CLASSES = [
    "rest_framework.authentication.SessionAuthentication",
]
DEFAULT_ADMIN_API_PERMISSION_CLASSES = [
    "rest_framework.permissions.IsAdminUser",
]

# Defaults for "public" endpoints (hash / token authenticated, e.g. the
# unsubscribe link clicked from an email).  No auth, no permission classes.
DEFAULT_PUBLIC_API_AUTHENTICATION_CLASSES: list[str] = []
DEFAULT_PUBLIC_API_PERMISSION_CLASSES: list[str] = []


class EmailsAppSettings:
    @property
    def app_settings(self) -> dict:
        return getattr(settings, "EMAILS_APP", {}) or {}

    def _import_class_paths(self, class_paths):
        return [import_string(class_path) for class_path in class_paths]

    @property
    def config_path(self) -> Path:
        configured_path = self.app_settings.get(
            "CONFIG_PATH", getattr(settings, "EMAILS_CONFIG_PATH", DEFAULT_EMAILS_CONFIG_PATH)
        )
        config_path = Path(configured_path)
        if not config_path.is_absolute():
            config_path = Path(settings.BASE_DIR) / config_path
        return config_path

    @property
    def api_authentication_classes(self):
        class_paths = self.app_settings.get(
            "API_AUTHENTICATION_CLASSES",
            DEFAULT_API_AUTHENTICATION_CLASSES,
        )
        return self._import_class_paths(class_paths)

    @property
    def api_permission_classes(self):
        class_paths = self.app_settings.get(
            "API_PERMISSION_CLASSES",
            DEFAULT_API_PERMISSION_CLASSES,
        )
        return self._import_class_paths(class_paths)

    @property
    def admin_api_authentication_classes(self):
        class_paths = self.app_settings.get(
            "ADMIN_API_AUTHENTICATION_CLASSES",
            DEFAULT_ADMIN_API_AUTHENTICATION_CLASSES,
        )
        return self._import_class_paths(class_paths)

    @property
    def admin_api_permission_classes(self):
        class_paths = self.app_settings.get(
            "ADMIN_API_PERMISSION_CLASSES",
            DEFAULT_ADMIN_API_PERMISSION_CLASSES,
        )
        return self._import_class_paths(class_paths)

    @property
    def public_api_authentication_classes(self):
        class_paths = self.app_settings.get(
            "PUBLIC_API_AUTHENTICATION_CLASSES",
            DEFAULT_PUBLIC_API_AUTHENTICATION_CLASSES,
        )
        return self._import_class_paths(class_paths)

    @property
    def public_api_permission_classes(self):
        class_paths = self.app_settings.get(
            "PUBLIC_API_PERMISSION_CLASSES",
            DEFAULT_PUBLIC_API_PERMISSION_CLASSES,
        )
        return self._import_class_paths(class_paths)


emails_settings = EmailsAppSettings()
