from rest_framework.permissions import BasePermission

from management.permissions import ManagementPermission


class HasOpenChatAccess(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perm(ManagementPermission.OPEN_CHAT_ACCESS)
        )


class HasEditOpenChatConfiguration(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perm(ManagementPermission.EDIT_OPEN_CHAT_CONFIGURATION)
        )


class HasManageOpenChatAccess(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perm(ManagementPermission.MANAGE_OPEN_CHAT_ACCESS)
        )


class OpenChatConfigurationPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method == "GET":
            return request.user.has_perm(ManagementPermission.OPEN_CHAT_ACCESS)
        if request.method in ("POST", "PUT"):
            return request.user.has_perm(ManagementPermission.EDIT_OPEN_CHAT_CONFIGURATION)
        return False
