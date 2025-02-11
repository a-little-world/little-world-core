from rest_framework.permissions import BasePermission


class IsAdminOrMatchingUser(BasePermission):
    """
    Allows access only to admin users.
    """

    def has_permission(self, request, view):
        from management.models.state import State

        return bool(request.user and request.user.is_staff) or bool(
            request.user
            and request.user.is_authenticated
            and request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
        )
