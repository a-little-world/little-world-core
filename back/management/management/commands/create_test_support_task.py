"""
Creates test SupportTasks covering all action types.

Usage:
    python manage.py create_test_support_task <user_email>
    python manage.py create_test_support_task <user_email> --type support_reply
    python manage.py create_test_support_task <user_email> --type all

Available types:
    support_reply               HelpMessage → send_support_reply action
    change_user_type            Profile → message_action_change_user_type
    wrong_user_type             Profile → profile_action_wrong_user_type
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
    "wrong_user_type",
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
    from admin_tasks.models import SupportTask

    from management.models.help_message import HelpMessage

    help_message = HelpMessage.objects.create(
        user=user,
        message="This is a test support message. Please help me!",
        kind=HelpMessage.KindChoices.GENERAL,
    )
    task = SupportTask.objects.filter(metadata__help_message_id=help_message.id).first()
    if task is None:
        raise RuntimeError("Signal did not create a task — check admin_tasks signals are connected.")
    return task


def _create_change_user_type(cmd, user):
    from admin_tasks.models import SupportTask, SupportTaskAction

    from management.models.profile import Profile

    profile = Profile.objects.get(user=user)
    task = SupportTask.objects.create(
        title=f"Change user type — {user.email}",
        description="User requested a user type change via support.",
        related_object=profile,
        metadata={"user_id": user.id},
    )
    SupportTaskAction.objects.create(
        task=task,
        action_type="message_action_change_user_type",
        static_parameters={"user_id": user.id},
        parameters={"user_type": profile.user_type or "mentee"},
    )
    return task


def _create_wrong_user_type(cmd, user):
    from admin_tasks.models import SupportTask, SupportTaskAction

    from management.models.profile import Profile

    profile = Profile.objects.get(user=user)
    task = SupportTask.objects.create(
        title=f"Wrong user type detected — {user.email}",
        description="Profile user type does not match stated background.",
        related_object=profile,
        metadata={"user_id": user.id},
    )
    SupportTaskAction.objects.create(
        task=task,
        action_type="profile_action_wrong_user_type",
        static_parameters={"user_id": user.id},
        parameters={"user_type": "mentee"},
    )
    return task


def _create_change_profile_value(cmd, user):
    from admin_tasks.models import SupportTask, SupportTaskAction

    from management.models.profile import Profile

    profile = Profile.objects.get(user=user)
    task = SupportTask.objects.create(
        title=f"Change profile value — {user.email}",
        description="User requested correction of a profile field via support.",
        related_object=profile,
        metadata={"user_id": user.id},
    )
    SupportTaskAction.objects.create(
        task=task,
        action_type="message_action_change_profile_value",
        static_parameters={"user_id": user.id, "field": "description"},
        parameters={"value": "Updated description from support request."},
    )
    return task


def _create_country_of_residence(cmd, user):
    from admin_tasks.models import SupportTask, SupportTaskAction

    from management.models.profile import Profile

    profile = Profile.objects.get(user=user)
    task = SupportTask.objects.create(
        title=f"Update country of residence — {user.email}",
        description="Profile country of residence needs correction.",
        related_object=profile,
        metadata={"user_id": user.id},
    )
    SupportTaskAction.objects.create(
        task=task,
        action_type="profile_change_action_country_of_residence",
        static_parameters={"user_id": user.id},
        parameters={"country_of_residence": "DE"},
    )
    return task


def _create_remove_match(cmd, user):
    from admin_tasks.models import SupportTask, SupportTaskAction
    from django.db.models import Q

    from management.models.matches import Match

    match = Match.objects.filter(active=True).filter(Q(user1=user) | Q(user2=user)).first()
    if match is None:
        raise RuntimeError(f"No active match found for {user.email}")

    task = SupportTask.objects.create(
        title=f"Remove match — {match.uuid}",
        description="Match flagged for removal via support request.",
        related_object=match,
        metadata={"match_uuid": str(match.uuid), "user_id": user.id},
    )
    SupportTaskAction.objects.create(
        task=task,
        action_type="message_action_remove_match",
        static_parameters={"match_uuid": str(match.uuid)},
        parameters={"reason": "Test: user requested match removal."},
    )
    return task


def _create_scoring_assessment(cmd, user):
    from admin_tasks.models import SupportTask, SupportTaskAction

    from management.models.profile import Profile

    profile = Profile.objects.get(user=user)
    task = SupportTask.objects.create(
        title=f"Profile scoring review — {user.email}",
        description="Profile scheduled for quality scoring review.",
        related_object=profile,
        metadata={"user_id": user.id},
    )
    SupportTaskAction.objects.create(
        task=task,
        action_type="scoring_profile_assessment",
        static_parameters={"user_id": user.id},
        parameters={"decision": "approve"},
    )
    return task


def _create_suspicious_profile(cmd, user):
    from admin_tasks.models import SupportTask, SupportTaskAction

    from management.models.profile import Profile

    profile = Profile.objects.get(user=user)
    task = SupportTask.objects.create(
        title=f"Suspicious profile — {user.email}",
        description="Profile flagged: spam keywords detected in description.",
        related_object=profile,
        metadata={"user_id": user.id},
    )
    SupportTaskAction.objects.create(
        task=task,
        action_type="profile_action_suspicious_profile",
        static_parameters={"user_id": user.id, "reason": "Spam keywords detected"},
        parameters={"decision": "dismiss"},
    )
    return task


def _create_too_empty_profile(cmd, user):
    from admin_tasks.models import SupportTask, SupportTaskAction

    from management.models.profile import Profile

    profile = Profile.objects.get(user=user)
    task = SupportTask.objects.create(
        title=f"Incomplete profile — {user.email}",
        description="Profile is missing: description, birth_year.",
        related_object=profile,
        metadata={"user_id": user.id},
    )
    SupportTaskAction.objects.create(
        task=task,
        action_type="profile_action_too_empty_profile",
        static_parameters={
            "user_id": user.id,
            "missing_fields": ["description", "birth_year"],
        },
        parameters={"decision": "contact_user", "contact_message": ""},
    )
    return task


_CREATORS = {
    "support_reply": _create_support_reply,
    "change_user_type": _create_change_user_type,
    "wrong_user_type": _create_wrong_user_type,
    "change_profile_value": _create_change_profile_value,
    "country_of_residence": _create_country_of_residence,
    "remove_match": _create_remove_match,
    "scoring_assessment": _create_scoring_assessment,
    "suspicious_profile": _create_suspicious_profile,
    "too_empty_profile": _create_too_empty_profile,
}
