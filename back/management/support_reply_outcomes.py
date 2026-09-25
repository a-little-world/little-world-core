"""Helpers to record and close Open Chat support-reply outcomes.

The Open Chat reply-suggestion interaction runs after the support task already
exists, so outcomes are recorded as notes on the task and the single related
``SupportTaskAction`` is resolved when the outcome closes the ticket.
"""

from __future__ import annotations

from django.db.models import Q

from management.models.support_task import SupportTask, SupportTaskAction, SupportTaskNote

READ_CLOSURE_NOTE = "Message marked as read and ticket closed."


def find_open_support_reply_action_for_user(user, *, message_uuid: str | None = None) -> SupportTaskAction | None:
    """Return the most recent open ``support_reply`` action for a user.

    When ``message_uuid`` is given the match is narrowed to that source message,
    otherwise it falls back to the user's recipient/related-user open action.
    """
    actions = SupportTaskAction.objects.select_related("task").filter(
        action_type="support_reply",
        status=SupportTaskAction.Status.OPEN,
        task__status__in=[SupportTask.Status.NEW, SupportTask.Status.IN_PROGRESS],
    )
    if message_uuid is not None:
        actions = actions.filter(static_parameters__message_uuid=str(message_uuid))
    else:
        actions = actions.filter(Q(static_parameters__recipient_user_id=user.pk) | Q(task__related_user_id=user.pk))
    return actions.order_by("-task_id").first()


def log_support_reply_outcome(action: SupportTaskAction, actor, text: str) -> SupportTaskNote:
    """Record a support-task note attributed to the acting support user."""
    note = SupportTaskNote(task=action.task, text=text, created_by=actor)
    note.save(changed_by=actor)
    return note


def close_support_reply_task_for_read_message(
    user,
    *,
    actor,
    message,
) -> SupportTaskAction | None:
    """Log and close the open support-reply task when a message is marked as read."""
    action = find_open_support_reply_action_for_user(user, message_uuid=getattr(message, "uuid", None))
    if action is None:
        action = find_open_support_reply_action_for_user(user)
    if action is None:
        return None
    log_support_reply_outcome(action, actor, READ_CLOSURE_NOTE)
    action.resolve(SupportTaskAction.Status.EXECUTED, actor)
    return action
