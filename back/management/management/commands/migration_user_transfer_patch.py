from django.core.management.base import BaseCommand

from management.controller import get_base_management_user, make_tim_support_user
from management.models.user import User
from management.permissions import ManagementPermission


class Command(BaseCommand):
    def handle(self, **options):
        bs = get_base_management_user()
        # TODO: deprecated - replace legacy state.managed_users filtering with managed_users_queryset().
        all_new_matching_user_managed = bs.managed_users_queryset(active_only=False)
        all_users_to_transfer = (
            User.objects.all()
            .exclude(id__in=all_new_matching_user_managed)
            .exclude(
                user_permissions__content_type__app_label="management",
                user_permissions__content_type__model="state",
                user_permissions__codename=ManagementPermission.MATCHING_USER.codename,
            )
            .exclude(is_staff=True)
        )

        print(f"Currently already managed users: {all_new_matching_user_managed.count()}")
        print(f"Users to transfer: {all_users_to_transfer.count()}")

        c = 0
        for user in all_users_to_transfer:
            c += 1
            print(f"Transferring user {c} of {all_users_to_transfer.count()}")
            make_tim_support_user(user, send_message=False)
