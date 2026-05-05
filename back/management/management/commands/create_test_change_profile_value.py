"""
Creates a test task for changing a profile value.

Usage:
    python manage.py create_test_change_profile_value <user_email> --field country_of_residence
    python manage.py create_test_change_profile_value <user_email> --field birth_year --value 1990
"""

from django.core.management.base import BaseCommand, CommandError

from management.models.user import User
from management.models.profile import Profile


ALLOWED_FIELDS = [
    "country_of_residence",
    "birth_year",
    "description",
    "first_name",
    "second_name",
    "phone_mobile",
]


class Command(BaseCommand):
    help = "Create a test AdminTask to change a profile value"

    def add_arguments(self, parser):
        parser.add_argument("user_email", type=str, help="Email of the user")
        parser.add_argument(
            "--field",
            type=str,
            required=True,
            choices=ALLOWED_FIELDS,
            help="Profile field to change",
        )
        parser.add_argument(
            "--value",
            type=str,
            default="",
            help="New value for the field",
        )
        parser.add_argument(
            "--from-message",
            action="store_true",
            help="Create from support message context",
        )

    def handle(self, **options):
        email = options["user_email"]
        field = options["field"]
        value = options["value"]
        from_message = options["from_message"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email '{email}'")

        profile = Profile.objects.filter(user=user).first()
        if profile is None:
            raise CommandError(f"No profile found for user '{email}'")

        current_value = getattr(profile, field, None)

        from admin_tasks.models import AdminTask, AdminTaskAction

        if from_message or field == "country_of_residence":
            if from_message:
                action_type = "message_action_change_profile_value"
            else:
                action_type = "profile_change_action_country_of_residence"
        else:
            action_type = "message_action_change_profile_value"

        task = AdminTask.objects.create(
            title=f"Update {field} for {email}",
            description=f"Change {field} from '{current_value}' to '{value or '[new value]'}'",
            metadata={"user_id": user.id, "field": field},
        )

        action = AdminTaskAction.objects.create(
            task=task,
            action_type=action_type,
            static_parameters={
                "user_id": user.id,
                "field": field,
                "current_value": current_value or "",
            },
            parameters={"new_value": value},
        )

        self.stdout.write(f"AdminTask #{task.id} created: '{task.title}'")
        self.stdout.write(f"  Action: {action_type}")
        self.stdout.write(f"  Field: {field}")
        self.stdout.write(f"  Current value: {current_value or '(empty)'}")
        self.stdout.write(f"  Proposed value: {value or '(empty)'}")
        self.stdout.write(self.style.SUCCESS(f"\nDone. View in admin panel: /tasks/{task.id}"))
