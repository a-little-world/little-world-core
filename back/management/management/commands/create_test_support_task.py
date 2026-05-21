"""
Creates test SupportTasks covering all action types.

Usage:
    python manage.py create_test_support_task <user_email>
    python manage.py create_test_support_task <user_email> --type support_reply
    python manage.py create_test_support_task <user_email> --type all

Available types:
    support_reply               HelpMessage → support_reply action
    change_user_type            Profile → message_action_change_user_type
    country_of_residence        Profile → profile_change_action_country_of_residence
    all                         Create one task of each type above
"""

from django.core.management.base import BaseCommand, CommandError

TASK_TYPES = [
    "support_reply",
    "change_user_type",
    "country_of_residence",
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


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_staff_user():
    from management.models.user import User

    staff = User.objects.filter(is_staff=True).first()
    if staff is None:
        raise RuntimeError("No staff user found — cannot set created_by.")
    return staff


def _user_name(user) -> str:
    from management.models.profile import Profile

    try:
        profile = Profile.objects.get(user=user)
        return f"{profile.first_name} {profile.second_name}".strip() or f"#{user.id}"
    except Profile.DoesNotExist:
        return f"#{user.id}"


# ─── Creators ─────────────────────────────────────────────────────────────────


def _create_support_reply(cmd, user):
    from management.models.help_message import HelpMessage
    from management.models.support_task import SupportTask

    help_message = HelpMessage.objects.create(
        user=user,
        message="This is a test support message. Please help me!",
        kind=HelpMessage.KindChoices.GENERAL,
    )
    return SupportTask.create_of_type(
        "support_reply",
        static_parameters={
            "help_message_id": help_message.id,
            "kind_display": help_message.get_kind_display(),
            "message_preview": help_message.message[:500],
        },
        parameters={"message": ""},
        related_user=user,
        created_by=_get_staff_user(),
    )


def _create_change_user_type(cmd, user):
    from management.models.profile import Profile
    from management.models.support_task import SupportTask

    profile = Profile.objects.get(user=user)
    return SupportTask.create_of_type(
        "change_user_type",
        static_parameters={
            "help_message_id": 0,
            "user_id": user.id,
            "user_name": _user_name(user),
            "current_value": profile.user_type or "mentee",
        },
        parameters={"new_value": profile.user_type or "mentee"},
        related_user=user,
        created_by=_get_staff_user(),
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
            "user_name": _user_name(user),
            "current_value": profile.country_of_residence or "",
        },
        parameters={"new_value": "DE"},
        related_user=user,
        created_by=_get_staff_user(),
    )


_CREATORS = {
    "support_reply":       _create_support_reply,
    "change_user_type":    _create_change_user_type,
    "country_of_residence": _create_country_of_residence,
}
