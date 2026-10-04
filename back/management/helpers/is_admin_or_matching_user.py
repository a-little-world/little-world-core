from rest_framework.permissions import BasePermission

from management.permissions import SUPPORT_USER_PERMISSIONS, ManagementPermission


class IsAdminOrMatchingUser(BasePermission):
    """
    Allows access only to admin users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff) or bool(
            request.user and request.user.is_authenticated and request.user.has_perm(ManagementPermission.MATCHING_USER)
        )


class IsAdminOrSupportUser(BasePermission):
    """Allows access to admin users and any member of the support team.

    A support user is staff/superuser or holds one of the support-related
    management permissions (matching operations, support message replies, main
    support account).
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        return any(user.has_perm(permission) for permission in SUPPORT_USER_PERMISSIONS)
