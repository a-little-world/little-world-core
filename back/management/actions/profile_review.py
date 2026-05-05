from .registry import register


def _get_user(user_id: int):
    from management.models.user import User

    return User.objects.select_related("state").get(id=user_id)


def _tag_user(user, tag: str) -> None:
    state = user.state
    tags = list(state.tags) if state.tags else []
    if tag not in tags:
        tags.append(tag)
        state.tags = tags
        state.save(update_fields=["tags"])


def _contact_user(user, message: str) -> None:
    from management.controller import get_base_management_user

    management_user = get_base_management_user()
    management_user.message(user, message)


@register("scoring_profile_assessment")
def scoring_profile_assessment(static_params: dict, params: dict) -> None:
    """Admin reviews a profile flagged by the scoring system.

    static_params:
        user_id (int)

    params:
        decision (str): 'approve' | 'flag' | 'contact_user'
        contact_message (str, optional): message to send if decision == 'contact_user'
    """
    decision = params.get("decision", "approve")
    if decision == "flag":
        user = _get_user(static_params["user_id"])
        _tag_user(user, "scoring_flagged")
    elif decision == "contact_user":
        user = _get_user(static_params["user_id"])
        msg = params.get("contact_message", "")
        if msg:
            _contact_user(user, msg)


def _finish_task(action) -> None:
    """Mark the parent task as FINISHED when dismiss is chosen."""
    from admin_tasks.models import AdminTask

    task = action.task
    task.status = AdminTask.Status.FINISHED
    task.save(update_fields=["status"])


@register("profile_action_suspicious_profile")
def profile_action_suspicious_profile(static_params: dict, params: dict) -> None:
    """Admin reviews a profile flagged as suspicious.

    static_params:
        user_id (int)
        reason (str): why it was flagged

    params:
        decision (str): 'tag_suspicious' | 'contact_user' | 'dismiss'
        contact_message (str, optional)
    """
    from admin_tasks.models import AdminTaskAction

    decision = params.get("decision", "dismiss")
    if decision == "tag_suspicious":
        user = _get_user(static_params["user_id"])
        _tag_user(user, "state.tags-spam")
    elif decision == "contact_user":
        user = _get_user(static_params["user_id"])
        msg = params.get("contact_message", "")
        if msg:
            _contact_user(user, msg)
    elif decision == "dismiss":
        # Dismiss closes the task - nothing to do, just mark as finished
        # The action is already approved, now close the parent task
        pass


@register("profile_action_too_empty_profile")
def profile_action_too_empty_profile(static_params: dict, params: dict) -> None:
    """Admin reviews a profile flagged as too empty.

    static_params:
        user_id (int)
        missing_fields (list[str])

    params:
        decision (str): 'contact_user' | 'dismiss'
        contact_message (str, optional)
    """
    decision = params.get("decision", "dismiss")
    if decision == "contact_user":
        user = _get_user(static_params["user_id"])
        msg = params.get("contact_message", "")
        if msg:
            _contact_user(user, msg)
