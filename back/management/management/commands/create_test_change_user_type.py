"""
Creates a test task for changing a user's type.

Usage:
    python manage.py create_test_change_user_type <user_email>
    python manage.py create_test_change_user_type <user_email> --from-message
    python manage.py create_test_change_user_type <user_email> --new-type volunteer
"""

from django.core.management.base import BaseCommand, CommandError

from management.models.user import User
from management.models.profile import Profile


class Command(BaseCommand):
    help = "Create a test AdminTask to change a user's type"

    def add_arguments(self, parser):
        parser.add_argument("user_email", type=str, help="Email of the user")
        parser.add_argument(
            "--from-message",
            action="store_true",
            help="Create from support message context (message_action_change_user_type)",
        )
        parser.add_argument(
            "--new-type",
            type=str,
            default="volunteer",
            choices=["learner", "volunteer"],
            help="Target user type",
        )
        parser.add_argument(
            "--reason",
            type=str,
            default="",
            help="Reason for the change",
        )

    def handle(self, **options):
        email = options["user_email"]
        from_message = options["from_message"]
        new_type = options["new_type"]
        reason = options["reason"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email '{email}'")

        profile = Profile.objects.filter(user=user).first()
        if profile is None:
            raise CommandError(f"No profile found for user '{email}'")

        current_type = profile.user_type

        from admin_tasks.models import AdminTask, AdminTaskAction

        if from_message:
            # message_action_change_user_type
            action_type = "message_action_change_user_type"
            title = f"Change user type for {email}"
        else:
            # profile_action_wrong_user_type
            action_type = "profile_action_wrong_user_type"
            title = f"Correct user type for {email}"

        task = AdminTask.objects.create(
            title=title,
            description=reason or f"Change user type from '{current_type}' to '{new_type}'",
            metadata={"user_id": user.id, "current_user_type": current_type},
        )

        action = AdminTaskAction.objects.create(
            task=task,
            action_type=action_type,
            static_parameters={
                "user_id": user.id,
                "current_user_type": current_type,
            },
            parameters={"new_user_type": new_type},
        )

        self.stdout.write(f"AdminTask #{task.id} created: '{task.title}'")
        self.stdout.write(f"  Action: {action_type}")
        self.stdout.write(f"  Current type: {current_type}")
        self.stdout.write(f"  Proposed type: {new_type}")
        self.stdout.write(self.style.SUCCESS(f"\nDone. View in admin panel: /tasks/{task.id}"))
