"""
Creates test SupportTasks covering all action types.

Usage:
    python manage.py create_test_support_task <user_email>
    python manage.py create_test_support_task <user_email> --type support_reply
    python manage.py create_test_support_task <user_email> --type all

Available types:
    support_reply               HelpMessage → support_reply action
    change_user_type            Profile → message_action_change_user_type
    change_profile_value        Profile → message_action_change_profile_value
    country_of_residence        Profile → profile_change_action_country_of_residence
    remove_match                Match   → message_action_remove_match
    scoring_assessment          Profile → scoring_profile_assessment
    suspicious_profile          Profile → profile_action_suspicious_profile
    too_empty_profile           Profile → profile_action_too_empty_profile
    all                         Create one task of each type above
"""

from django.core.management.base import BaseCommand, CommandError

TASK_TYPES = [
    "support_reply",
    "change_user_type",
    "change_profile_value",
    "country_of_residence",
    "remove_match",
    "scoring_assessment",
    "suspicious_profile",
    "too_empty_profile",
]


class Command(BaseCommand):
    help = "Create test SupportTasks for development"

    def add_arguments(self, parser):
        parser.add_argument("user_email", type=str)
        parser.add_argument(
            "--type",
            type=str,
            default="all",
            choices=TASK_TYPES + ["all"],
            help="Which task type to create (default: all)",
        )

    def handle(self, **options):
        from management.models.user import User

        email = options["user_email"]
        task_type = options["type"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email '{email}'")

        types_to_create = TASK_TYPES if task_type == "all" else [task_type]

        for t in types_to_create:
            try:
                task = _CREATORS[t](self, user)
                self.stdout.write(self.style.SUCCESS(f"[{t}] SupportTask #{task.id}: '{task.title}'"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[{t}] Failed: {e}"))


# ─── Creators ─────────────────────────────────────────────────────────────────


def _create_support_reply(cmd, user):
    from management.models.help_message import HelpMessage
    from management.models.support_task import SupportTask

    help_message = HelpMessage.objects.create(
        user=user,
        message="This is a test support message. Please help me!",
        kind=HelpMessage.KindChoices.GENERAL,
    )
    task = SupportTask.objects.filter(related_user=user, actions__action_type="support_reply").first()
    if task is None:
        raise RuntimeError("Signal did not create a task — check signals are connected.")
    return task


def _create_change_user_type(cmd, user):
    from management.models.profile import Profile
    from management.models.support_task import SupportTask

    profile = Profile.objects.get(user=user)
    return SupportTask.create_of_type(
        "change_user_type",
        static_parameters={
            "help_message_id": 0,
            "user_id": user.id,
            "current_value": profile.user_type or "mentee",
        },
        parameters={"new_value": profile.user_type or "mentee"},
        related_user=user,
    )


def _create_change_profile_value(cmd, user):
    from management.models.support_task import SupportTask

    return SupportTask.create_of_type(
        "change_profile_value",
        static_parameters={"help_message_id": 0, "user_id": user.id, "field": "description"},
        parameters={"new_value": "Updated description from support request."},
        related_user=user,
    )


def _create_country_of_residence(cmd, user):
    from management.models.profile import Profile
    from management.models.support_task import SupportTask

    profile = Profile.objects.get(user=user)
    return SupportTask.create_of_type(
        "change_country_of_residence",
        static_parameters={
            "help_message_id": 0,
            "user_id": user.id,
            "current_value": profile.country_of_residence or "",
        },
        parameters={"new_value": "DE"},
        related_user=user,
    )


def _create_remove_match(cmd, user):
    from django.db.models import Q

    from management.models.matches import Match
    from management.models.support_task import SupportTask

    match = Match.objects.filter(active=True).filter(Q(user1=user) | Q(user2=user)).first()
    if match is None:
        raise RuntimeError(f"No active match found for {user.email}")

    return SupportTask.create_of_type(
        "remove_match",
        static_parameters={"help_message_id": 0, "user_id": user.id, "match_id": match.id},
        parameters={"reason": "Test: user requested match removal."},
        related_user=user,
    )


def _create_scoring_assessment(cmd, user):
    from management.models.support_task import SupportTask

    return SupportTask.create_of_type(
        "scoring_assessment",
        static_parameters={"user_id": user.id},
        parameters={"decision": "approve"},
        related_user=user,
    )


def _create_suspicious_profile(cmd, user):
    from management.models.support_task import SupportTask

    return SupportTask.create_of_type(
        "suspicious_profile",
        static_parameters={"user_id": user.id, "reason": "Spam keywords detected"},
        parameters={"decision": "dismiss"},
        related_user=user,
    )


def _create_too_empty_profile(cmd, user):
    from management.models.support_task import SupportTask

    return SupportTask.create_of_type(
        "too_empty_profile",
        static_parameters={
            "user_id": user.id,
            "missing_fields": ["description", "birth_year"],
        },
        parameters={"decision": "contact_user", "contact_message": ""},
        related_user=user,
    )


_CREATORS = {
    "support_reply": _create_support_reply,
    "change_user_type": _create_change_user_type,
    "change_profile_value": _create_change_profile_value,
    "country_of_residence": _create_country_of_residence,
    "remove_match": _create_remove_match,
    "scoring_assessment": _create_scoring_assessment,
    "suspicious_profile": _create_suspicious_profile,
    "too_empty_profile": _create_too_empty_profile,
}
