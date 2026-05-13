# from django.db.models.signals import post_save


def connect_signals() -> None:
    """Connect all support task signals. Called from ManagementConfig.ready()."""
    # from management.models.help_message import HelpMessage
    # from management.models.profile import Profile

    # post_save.connect(_create_task_for_help_message, sender=HelpMessage)
    # post_save.connect(_check_profile_on_save, sender=Profile)


# ─── HelpMessage → task creation ──────────────────────────────────────────────


def _create_support_reply(sender, instance, created, **kwargs) -> None:
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


def _cancel_open_task(user_id: int, action_type: str) -> None:
    """Cancel any open task of the given action_type for the user so a fresh one can be created."""
    from management.models.support_task import SupportTaskAction

    for action in SupportTaskAction.objects.select_related("task").filter(
        action_type=action_type,
        task__related_user_id=user_id,
        task__status__in=["NEW", "IN_PROGRESS"],
        status="OPEN",
    ):
        action.resolve(SupportTaskAction.Status.CANCELLED, reviewed_by=None)


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

    _cancel_open_task(profile.user_id, "profile_action_too_empty_profile")
    if missing:
        from management.models.support_task import SupportTask

        task = SupportTask.create_of_type(
            "too_empty_profile",
            static_parameters={
                "user_id": profile.user_id,
                "user_name": f"{profile.first_name} {profile.second_name}",
                "missing_fields": missing,
            },
            parameters={"decision": "contact_user", "contact_message": ""},
            related_user_id=profile.user_id,
        )
        created_tasks.append({"type": "too_empty", "task_id": task.pk})

    # ── Suspicious profile ────────────────────────────────────────────────────
    suspicious_reasons = _detect_suspicious_profile(profile)

    _cancel_open_task(profile.user_id, "profile_action_suspicious_profile")
    if suspicious_reasons:
        from management.models.support_task import SupportTask

        task = SupportTask.create_of_type(
            "suspicious_profile",
            static_parameters={
                "user_id": profile.user_id,
                "user_name": f"{profile.first_name} {profile.second_name}",
                "reason": suspicious_reasons[0],
            },
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
