from django.core.management.base import BaseCommand

from management.models.user import User
from management.user_journey import PerUserBuckets


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument("arg1", type=str, help="User uuid")

    def handle(self, **options):
        user_uuid = options["arg1"]

        if user_uuid == "all":
            buckets = PerUserBuckets.categorize_all_users()
            print(f"Users have been categorized into buckets: {buckets}")
        else:
            user = User.objects.filter(uuid=user_uuid)
            bucket = PerUserBuckets.categorize_user(user)

            print("User is in bucket: ", bucket)
