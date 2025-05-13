from django.core.management.base import BaseCommand

from management.models.user import User


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument("arg1", type=str, help="User email")
        parser.add_argument("arg2", type=str, help="Notification headline", default="Test notification", nargs="?")
        parser.add_argument("arg3", type=str, help="Notification title", default="Test notification", nargs="?")
        parser.add_argument(
            "arg4", type=str, help="Notification description", default="This is a test notification", nargs="?"
        )
        parser.add_argument("arg5", type=int, help="Notification count", default="1", nargs="?")

    def handle(self, **options):
        email = options["arg1"]
        headline = options["arg2"]
        title = options["arg3"]
        description = options["arg4"]
        count = options["arg5"]

        user = User.objects.get(email=email)
        for i in range(count):
            title = title + (" " + str(i + 1) if count != 1 else "")
            user.notification(headline=headline, title=title, description=description, show_toast=True)
