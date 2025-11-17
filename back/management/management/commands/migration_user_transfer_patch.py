from django.core.management.base import BaseCommand

from management.models.user import User
from management.controller import make_tim_support_user, get_base_management_user


class Command(BaseCommand):

    def handle(self, **options):
        bs = get_base_management_user()
        all_new_matching_user_managed = bs.state.managed_users.all()
        all_users_to_transfer = User.objects.all().exclude(
            id__in=all_new_matching_user_managed).exclude(
                state__extra_user_permissions__contains="matching-user").exclude(
                        is_staff=True)
                
        print(f"Currently already managed users: {all_new_matching_user_managed.count()}")
        print(f"Users to transfer: {all_users_to_transfer.count()}")

        c = 0
        for user in all_users_to_transfer:
            c += 1
            print(f"Transferring user {c} of {all_users_to_transfer.count()}")
            make_tim_support_user(user, send_message=False)