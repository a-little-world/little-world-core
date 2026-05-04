from enum import StrEnum

from django.contrib.auth.models import Permission


class ManagementPermission(StrEnum):
    VIEW_API_SCHEMA = "management.view_api_schema"
    VIEW_DATABASE_SCHEMA = "management.view_database_schema"
    VIEW_DOCS = "management.view_docs"
    VIEW_EMAIL_TEMPLATES = "management.view_email_templates"
    VIEW_STATS = "management.view_stats"
    MATCHING_USER = "management.matching_user"
    UNCENSORED_ADMIN_MATCHER = "management.uncensored_admin_matcher"
    USE_RANDOM_CALLS = "management.use_random_calls"

    @property
    def codename(self) -> str:
        return self.split(".", 1)[1]

    def get_permission_object(self) -> Permission | None:
        try:
            return Permission.objects.get_by_natural_key(self.codename, "management", "state")
        except Permission.DoesNotExist:
            return None


MANAGEMENT_PERMISSION_LABELS: dict[ManagementPermission, str] = {
    ManagementPermission.VIEW_API_SCHEMA: "Can view API schema",
    ManagementPermission.VIEW_DATABASE_SCHEMA: "Can view database schema",
    ManagementPermission.VIEW_DOCS: "Can view docs",
    ManagementPermission.VIEW_EMAIL_TEMPLATES: "Can view email templates",
    ManagementPermission.VIEW_STATS: "Can view stats",
    ManagementPermission.MATCHING_USER: "Can perform matching operations",
    ManagementPermission.UNCENSORED_ADMIN_MATCHER: "Can perform uncensored matching",
    ManagementPermission.USE_RANDOM_CALLS: "Can use random calls feature",
}

MANAGEMENT_PERMISSION_DEFINITIONS = [(perm.codename, label) for perm, label in MANAGEMENT_PERMISSION_LABELS.items()]
