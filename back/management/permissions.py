from enum import StrEnum

from django.contrib.auth.models import Permission
from django.db.models import Q


class ManagementPermission(StrEnum):
    VIEW_API_SCHEMA = "management.view_api_schema"
    VIEW_DATABASE_SCHEMA = "management.view_database_schema"
    MATCHING_USER = "management.matching_user"
    USE_RANDOM_CALLS = "management.use_random_calls"
    OPEN_CHAT_ACCESS = "management.open_chat_access"
    EDIT_OPEN_CHAT_CONFIGURATION = "management.edit_open_chat_configuration"
    MANAGE_OPEN_CHAT_ACCESS = "management.manage_open_chat_access"
    APPLY_MANAGEMENT_PERMISSIONS = "management.apply_management_permissions"
    CAN_SEND_SUPPORT_MESSAGE_REPLIES = "management.can_send_support_message_replies"
    IS_MAIN_SUPPORT_ACCOUNT = "management.is_main_support_account"
    RECEIVES_FULL_USER_ACCESS = "management.receives_full_user_access"

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
    ManagementPermission.OPEN_CHAT_ACCESS: "Can access open chat",
    ManagementPermission.EDIT_OPEN_CHAT_CONFIGURATION: "Can edit open chat configuration",
    ManagementPermission.MANAGE_OPEN_CHAT_ACCESS: "Manage Open Chat Access",
    ManagementPermission.APPLY_MANAGEMENT_PERMISSIONS: "Can apply management permissions",
    ManagementPermission.CAN_SEND_SUPPORT_MESSAGE_REPLIES: "Can send support message replies",
    ManagementPermission.IS_MAIN_SUPPORT_ACCOUNT: "Is main support account",
    ManagementPermission.RECEIVES_FULL_USER_ACCESS: "Receives full user access for newly created users",
}

MANAGEMENT_PERMISSION_DEFINITIONS = [(perm.codename, label) for perm, label in MANAGEMENT_PERMISSION_LABELS.items()]


def users_with_effective_permission(permission: ManagementPermission):
    """Return active users who receive a permission directly, through a group, or as superusers."""
    from management.models.user import User

    permission_object = permission.get_permission_object()
    if permission_object is None:
        return User.objects.none()
    return (
        User.objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(user_permissions=permission_object) | Q(groups__permissions=permission_object))
        .distinct()
    )


def user_can_edit_management_permissions(user) -> bool:
    return bool(user.is_staff or user.has_perm(ManagementPermission.APPLY_MANAGEMENT_PERMISSIONS))


def user_can_grant_apply_management_permissions(user) -> bool:
    return bool(user.is_staff)


def user_can_manage_user_management_permissions(actor, target) -> bool:
    if actor.is_staff:
        return True
    if actor.has_management_access(target):
        return True
    return bool(
        actor.has_perm(ManagementPermission.APPLY_MANAGEMENT_PERMISSIONS)
        and target.has_perm(ManagementPermission.MATCHING_USER)
    )
