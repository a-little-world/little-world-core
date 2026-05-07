from django.db.models.signals import post_save


def connect_signals() -> None:
    """Connect all support task signals. Called from ManagementConfig.ready()."""
    from management.models.help_message import HelpMessage
    from management.models.profile import Profile

    post_save.connect(_create_task_for_help_message, sender=HelpMessage)
    post_save.connect(_check_profile_on_save, sender=Profile)


# ─── HelpMessage → task creation ──────────────────────────────────────────────


def _create_task_for_help_message(sender, instance, created, **kwargs) -> None:
    """Auto-create a support reply task whenever a new HelpMessage is submitted."""
    if not created:
        return

    from management.models.support_task import SupportTask

    SupportTask.create_of_type(
        "support_reply",
        static_parameters={
            "help_message_id": instance.id,
            "kind_display": instance.get_kind_display(),
            "message_preview": instance.message[:500],
        },
        parameters={"message": ""},
        related_user=instance.user,
    )


# ─── Profile save → system task creation ──────────────────────────────────────


def _open_task_exists(user_id: int, action_type: str) -> bool:
    """Guard: skip if a non-finished task with this action_type already exists for the user."""
    from management.models.support_task import SupportTaskAction

    return SupportTaskAction.objects.filter(
        action_type=action_type,
        task__related_user_id=user_id,
        task__status__in=["NEW", "IN_PROGRESS"],
        status="OPEN",
    ).exists()


def _check_profile_on_save(sender, instance, created, **kwargs) -> None:
    """Create system tasks when a profile is saved with issues."""
    # Skip on initial creation — user hasn't had a chance to fill in anything yet
    if created:
        return

    check_user_profile(instance)


def check_user_profile(profile) -> dict:
    """Check profile for completeness and suspicious patterns; create tasks as needed.

    Called both from the post_save signal and externally (e.g. after form completion).
    Returns a dict with created task info for debugging/monitoring.
    """
    created_tasks = []

    # ── Incomplete profile ────────────────────────────────────────────────────
    missing = []
    if not profile.description:
        missing.append("description")
    if not profile.birth_year:
        missing.append("birth_year")

    if missing and not _open_task_exists(profile.user_id, "profile_action_too_empty_profile"):
        from management.models.support_task import SupportTask

        task = SupportTask.create_of_type(
            "too_empty_profile",
            static_parameters={"user_id": profile.user_id, "missing_fields": missing},
            parameters={"decision": "contact_user", "contact_message": ""},
            related_user_id=profile.user_id,
        )
        created_tasks.append({"type": "too_empty", "task_id": task.pk})

    # ── Suspicious profile ────────────────────────────────────────────────────
    suspicious_reasons = _detect_suspicious_profile(profile)

    if suspicious_reasons and not _open_task_exists(profile.user_id, "profile_action_suspicious_profile"):
        from management.models.support_task import SupportTask

        task = SupportTask.create_of_type(
            "suspicious_profile",
            static_parameters={"user_id": profile.user_id, "reason": suspicious_reasons[0]},
            parameters={"decision": "dismiss"},
            related_user_id=profile.user_id,
        )
        created_tasks.append({"type": "suspicious", "task_id": task.pk})

    return {"created_tasks": created_tasks}


def _detect_suspicious_profile(profile) -> list[str]:
    """Detect suspicious patterns in a profile. Returns reasons, or empty list if fine.

    TODO: Implement actual detection logic:
    - Spam keywords in description
    - Implausible birth year
    - Suspicious patterns in name
    """
    return []


# ─── Scoring assessment ────────────────────────────────────────────────────────


def create_scoring_assessment_tasks_for_user(user_id: int) -> None:
    """Create a scoring_profile_assessment task for a given user if not already open."""
    if _open_task_exists(user_id, "scoring_profile_assessment"):
        return

    from management.models.profile import Profile
    from management.models.support_task import SupportTask

    try:
        related_user_id = Profile.objects.values_list("user_id", flat=True).get(user_id=user_id)
    except Profile.DoesNotExist:
        related_user_id = user_id

    SupportTask.create_of_type(
        "scoring_assessment",
        static_parameters={"user_id": user_id},
        parameters={"decision": "approve"},
        related_user_id=related_user_id,
    )
