"""
Creates a test task for removing a match.

Usage:
    python manage.py create_test_remove_match <user_email> <match_id>
    python manage.py create_test_remove_match <user_email> <match_id> --reason "Incompatible schedules"
"""

from django.core.management.base import BaseCommand, CommandError

from management.models.user import User
from management.models.matches import Match


class Command(BaseCommand):
    help = "Create a test AdminTask to remove a match"

    def add_arguments(self, parser):
        parser.add_argument("user_email", type=str, help="Email of the user requesting removal")
        parser.add_argument("match_id", type=int, help="ID of the match to remove")
        parser.add_argument(
            "--reason",
            type=str,
            default="User requested match removal",
            help="Reason for removing the match",
        )

    def handle(self, **options):
        email = options["user_email"]
        match_id = options["match_id"]
        reason = options["reason"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email '{email}'")

        try:
            match = Match.objects.get(id=match_id)
        except Match.DoesNotExist:
            raise CommandError(f"No match found with ID {match_id}")

        from admin_tasks.models import AdminTask, AdminTaskAction

        task = AdminTask.objects.create(
            title=f"Remove match #{match_id}",
            description=f"User {email} requested removal of match #{match_id}",
            metadata={
                "user_id": user.id,
                "match_id": match_id,
                "match_users": [match.learner_id, match.volunteer_id],
            },
        )

        action = AdminTaskAction.objects.create(
            task=task,
            action_type="message_action_remove_match",
            static_parameters={
                "user_id": user.id,
                "match_id": match_id,
            },
            parameters={"reason": reason},
        )

        self.stdout.write(f"AdminTask #{task.id} created: '{task.title}'")
        self.stdout.write(f"  Match ID: {match_id}")
        self.stdout.write(f"  Requested by: {email}")
        self.stdout.write(f"  Proposed reason: {reason}")
        self.stdout.write(self.style.SUCCESS(f"\nDone. View in admin panel: /tasks/{task.id}"))
