from rest_framework.permissions import BasePermission

from management.permissions import ManagementPermission


class IsAdminOrMatchingUser(BasePermission):
    """
    Allows access only to admin users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff) or bool(
            request.user and request.user.is_authenticated and request.user.has_perm(ManagementPermission.MATCHING_USER)
        )
