from django.core.management.base import BaseCommand

from management.models.notifications import Notification
from management.models.user import User


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument("arg1", type=str, help="User email")
        parser.add_argument(
            "arg2", type=str, help="Notification title", default="Test notification"
        )
        parser.add_argument(
            "arg3",
            type=str,
            help="Notification description",
            default="This is a test notification",
        )

    def handle(self, **options):
        email = options["arg1"]
        title = options["arg2"]
        description = options["arg3"]

        user = User.objects.get(email=email)
        notification = Notification.objects.create(
            user=user, title=title, description=description
        )
        user.notify(notification=notification)
