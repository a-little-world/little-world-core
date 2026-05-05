from django.db.models.signals import post_save
from django.dispatch import receiver


def connect_signals() -> None:
    """Connect all admin_tasks signals. Called from AdminTasksConfig.ready()."""
    from management.models.help_message import HelpMessage
    from management.models.profile import Profile

    post_save.connect(_create_task_for_help_message, sender=HelpMessage)
    post_save.connect(_check_profile_on_save, sender=Profile)


# ─── HelpMessage → task creation ──────────────────────────────────────────────


def _create_task_for_help_message(sender, instance, created, **kwargs) -> None:
    """Auto-create a support reply task whenever a new HelpMessage is submitted."""
    if not created:
        return

    from .models import AdminTask, AdminTaskAction

    task = AdminTask.objects.create(
        title=f"Support request ({instance.get_kind_display()})",
        description=instance.message[:500],
        related_object=instance,
        metadata={
            "help_message_id": instance.id,
            "user_id": instance.user_id,
            "kind": instance.kind,
        },
    )

    # Always create a reply action
    AdminTaskAction.objects.create(
        task=task,
        action_type="send_support_reply",
        static_parameters={"help_message_id": instance.id},
        parameters={"message": ""},
    )


# ─── Profile save → system task creation ──────────────────────────────────────


def _open_task_exists(user_id: int, action_type: str) -> bool:
    """Guard: skip if a non-finished task with this action_type already exists for the user."""
    from .models import AdminTask, AdminTaskAction

    return AdminTaskAction.objects.filter(
        action_type=action_type,
        task__metadata__user_id=user_id,
        task__status__in=["NEW", "IN_PROGRESS"],
        status="PENDING",
    ).exists()


def _check_profile_on_save(sender, instance, created, **kwargs) -> None:
    """Create system tasks when a profile is saved with issues."""
    # Skip on initial creation — user hasn't had a chance to fill in anything yet
    if created:
        return

    _maybe_create_too_empty_task(instance)
    _maybe_create_suspicious_task(instance)


def _maybe_create_too_empty_task(profile) -> None:
    from .models import AdminTask, AdminTaskAction

    missing = []
    if not profile.description:
        missing.append("description")
    if not profile.birth_year:
        missing.append("birth_year")

    if not missing:
        return

    if _open_task_exists(profile.user_id, "profile_action_too_empty_profile"):
        return

    task = AdminTask.objects.create(
        title=f"Incomplete profile — user #{profile.user_id}",
        description=f"Profile is missing: {', '.join(missing)}",
        related_object=profile,
        metadata={"user_id": profile.user_id},
    )
    AdminTaskAction.objects.create(
        task=task,
        action_type="profile_action_too_empty_profile",
        static_parameters={
            "user_id": profile.user_id,
            "missing_fields": missing,
        },
        parameters={"decision": "contact_user", "contact_message": ""},
    )


def _maybe_create_suspicious_task(profile) -> None:
    """
    Placeholder: add real detection logic here (e.g. spam keywords, implausible data).
    Currently a no-op — extend as needed.
    """
    # TODO: Implement suspicious profile detection
    # Examples:
    # - Spam keywords in description
    # - Implausible birth year
    # - Suspicious patterns in name/location
    pass


def check_user_profile(profile) -> dict:
    """
    Check the user profile for completeness and suspiciousness.
    Creates corresponding admin tasks if issues are found.

    This function is called after form completion to ensure profile quality.

    Returns a dict with the created tasks info for debugging/monitoring.
    """
    created_tasks = []

    # Check for incomplete profile (missing required fields)
    missing = []
    if not profile.description:
        missing.append("description")
    if not profile.birth_year:
        missing.append("birth_year")

    if missing and not _open_task_exists(profile.user_id, "profile_action_too_empty_profile"):
        from .models import AdminTask, AdminTaskAction

        task = AdminTask.objects.create(
            title=f"Incomplete profile — user #{profile.user_id}",
            description=f"Profile is missing: {', '.join(missing)}",
            related_object=profile,
            metadata={"user_id": profile.user_id},
        )
        AdminTaskAction.objects.create(
            task=task,
            action_type="profile_action_too_empty_profile",
            static_parameters={
                "user_id": profile.user_id,
                "missing_fields": missing,
            },
            parameters={"decision": "contact_user", "contact_message": ""},
        )
        created_tasks.append({"type": "too_empty", "task_id": task.id})

    # Check for suspicious profile
    # TODO: Implement actual suspicious profile detection logic
    # For now, this is a placeholder that can be extended
    suspicious_reasons = _detect_suspicious_profile(profile)
    if suspicious_reasons and not _open_task_exists(profile.user_id, "profile_action_suspicious_profile"):
        from .models import AdminTask, AdminTaskAction

        task = AdminTask.objects.create(
            title=f"Suspicious profile — user #{profile.user_id}",
            description=f"Profile flagged: {', '.join(suspicious_reasons)}",
            related_object=profile,
            metadata={"user_id": profile.user_id},
        )
        AdminTaskAction.objects.create(
            task=task,
            action_type="profile_action_suspicious_profile",
            static_parameters={
                "user_id": profile.user_id,
                "reason": suspicious_reasons[0] if suspicious_reasons else "Flagged for review",
            },
            parameters={"decision": "dismiss"},
        )
        created_tasks.append({"type": "suspicious", "task_id": task.id})

    return {"created_tasks": created_tasks}


def _detect_suspicious_profile(profile) -> list:
    """
    Detect suspicious patterns in a profile.

    Returns a list of reasons why the profile is suspicious, or empty list if fine.

    TODO: Implement actual detection logic such as:
    - Spam keywords in description
    - Implausible birth year (too old/young)
    - Suspicious patterns in name
    - Known spam domains in contact info
    - Inconsistent location data
    """
    reasons = []

    # Placeholder: Add real detection logic here
    # Example checks:
    # if profile.description and _contains_spam(profile.description):
    #     reasons.append("Spam keywords detected")
    #
    # if profile.birth_year and (profile.birth_year < 1900 or profile.birth_year > timezone.now().year - 10):
    #     reasons.append("Implausible birth year")

    return reasons


# ─── Periodic task (Celery) for scoring assessment ────────────────────────────
# Register this in your Celery beat schedule:
#   "scoring-profile-assessment": {
#       "task": "admin_tasks.tasks.create_scoring_assessment_tasks",
#       "schedule": crontab(hour=3, minute=0),  # daily at 3am
#   }


def create_scoring_assessment_tasks_for_user(user_id: int) -> None:
    """Create a scoring_profile_assessment task for a given user if not already open."""
    if _open_task_exists(user_id, "scoring_profile_assessment"):
        return

    from management.models.profile import Profile

    from .models import AdminTask, AdminTaskAction

    try:
        profile = Profile.objects.get(user_id=user_id)
    except Profile.DoesNotExist:
        profile = None

    task = AdminTask.objects.create(
        title=f"Profile scoring review — user #{user_id}",
        related_object=profile,
        metadata={"user_id": user_id},
    )
    AdminTaskAction.objects.create(
        task=task,
        action_type="scoring_profile_assessment",
        static_parameters={"user_id": user_id},
        parameters={"decision": "approve"},
    )
