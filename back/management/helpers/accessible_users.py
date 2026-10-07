from django.contrib.auth import get_user_model
from django.db.models import QuerySet


def get_accessible_users(caller) -> QuerySet:
    """Users the caller may see in statistics: everyone for staff, managed users otherwise.

    ``User`` is resolved lazily because ``management.models`` imports this package.
    """
    users = get_user_model().objects.all()
    if not caller.is_staff:
        users = users.filter(id__in=caller.managed_users_queryset(active_only=False).values("id"))
    return users
