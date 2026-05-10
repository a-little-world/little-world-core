from enum import StrEnum

from django.contrib.auth.models import Permission


class ManagementPermission(StrEnum):
    VIEW_API_SCHEMA = "management.view_api_schema"
    VIEW_DATABASE_SCHEMA = "management.view_database_schema"
    MATCHING_USER = "management.matching_user"
    USE_RANDOM_CALLS = "management.use_random_calls"
    APPLY_MANAGEMENT_PERMISSIONS = "management.apply_management_permissions"

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
    ManagementPermission.MATCHING_USER: "Can perform matching operations",
    ManagementPermission.USE_RANDOM_CALLS: "Can use random calls feature",
    ManagementPermission.APPLY_MANAGEMENT_PERMISSIONS: "Can apply management permissions",
}

MANAGEMENT_PERMISSION_DEFINITIONS = [(perm.codename, label) for perm, label in MANAGEMENT_PERMISSION_LABELS.items()]
