"""
Creates test tasks for profile review actions.

Usage:
    python manage.py create_test_profile_review <user_email> --type scoring
    python manage.py create_test_profile_review <user_email> --type suspicious --reason "Spam keywords detected"
    python manage.py create_test_profile_review <user_email> --type too_empty
"""

from django.core.management.base import BaseCommand, CommandError

from management.models.user import User
from management.models.profile import Profile

REVIEW_TYPES = {
    "scoring": {
        "action_type": "scoring_profile_assessment",
        "title_prefix": "Profile scoring review",
        "description": "Profile flagged by scoring system for review",
    },
    "suspicious": {
        "action_type": "profile_action_suspicious_profile",
        "title_prefix": "Suspicious profile review",
        "description": "Profile flagged as potentially suspicious",
    },
    "too_empty": {
        "action_type": "profile_action_too_empty_profile",
        "title_prefix": "Incomplete profile review",
        "description": "Profile missing required information",
    },
}


class Command(BaseCommand):
    help = "Create a test AdminTask for profile review"

    def add_arguments(self, parser):
        parser.add_argument("user_email", type=str, help="Email of the user")
        parser.add_argument(
            "--type",
            type=str,
            required=True,
            choices=list(REVIEW_TYPES.keys()),
            help="Type of profile review task",
        )
        parser.add_argument(
            "--reason",
            type=str,
            default="",
            help="Reason for flagging (used for suspicious type)",
        )
        parser.add_argument(
            "--missing-fields",
            type=str,
            default="description,birth_year",
            help="Comma-separated list of missing fields (used for too_empty type)",
        )

    def handle(self, **options):
        email = options["user_email"]
        review_type = options["type"]
        reason = options["reason"]
        missing_fields_str = options["missing_fields"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email '{email}'")

        profile = Profile.objects.filter(user=user).first()
        if profile is None:
            raise CommandError(f"No profile found for user '{email}'")

        from admin_tasks.models import AdminTask, AdminTaskAction

        config = REVIEW_TYPES[review_type]

        # Build static parameters based on type
        static_params = {"user_id": user.id}

        if review_type == "suspicious":
            static_params["reason"] = reason or "Flagged for review"
        elif review_type == "too_empty":
            missing_fields = [f.strip() for f in missing_fields_str.split(",") if f.strip()]
            static_params["missing_fields"] = missing_fields

        # Default parameters
        if review_type == "scoring":
            default_params = {"decision": "approve"}
        elif review_type == "suspicious":
            default_params = {"decision": "dismiss"}
        else:  # too_empty
            default_params = {"decision": "contact_user", "contact_message": ""}

        task = AdminTask.objects.create(
            title=f"{config['title_prefix']} — {email}",
            description=config["description"],
            metadata={"user_id": user.id, "review_type": review_type},
        )

        action = AdminTaskAction.objects.create(
            task=task,
            action_type=config["action_type"],
            static_parameters=static_params,
            parameters=default_params,
        )

        self.stdout.write(f"AdminTask #{task.id} created: '{task.title}'")
        self.stdout.write(f"  Review type: {review_type}")
        self.stdout.write(f"  Action: {config['action_type']}")

        if review_type == "suspicious":
            self.stdout.write(f"  Flag reason: {static_params.get('reason')}")
        elif review_type == "too_empty":
            self.stdout.write(f"  Missing fields: {', '.join(static_params.get('missing_fields', []))}")

        self.stdout.write(self.style.SUCCESS(f"\nDone. View in admin panel: /tasks/{task.id}"))
