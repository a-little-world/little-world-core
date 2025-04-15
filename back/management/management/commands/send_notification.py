from django.core.management.base import BaseCommand

from management.models.notifications import Notification
from management.models.user import User


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument("arg1", type=str, help="User email")
        parser.add_argument("arg2", type=str, help="Notification title", default="Test notification", nargs="?")
        parser.add_argument(
            "arg3", type=str, help="Notification description", default="This is a test notification", nargs="?"
        )
        parser.add_argument("arg4", type=int, help="Notification count", default="1", nargs="?")

    def handle(self, **options):
        email = options["arg1"]
        title = options["arg2"]
        description = options["arg3"]
        count = options["arg4"]

        user = User.objects.get(email=email)
        for i in range(count):
            notification = Notification.objects.create(
                user=user, title=title + (" " + str(i + 1) if count != 1 else ""), description=description
            )
            user.notify(notification=notification)
