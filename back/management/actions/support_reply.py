from dataclasses import dataclass

from .registry import register, register_task_type

SUGGESTED_ACTIONS = ("reply", "mark_read", "slack_feedback", "keep_open")


@dataclass
class StaticParams:
    help_message_id: int | None = None
    kind_display: str = "General"  # e.g. "General", "Technical"
    message_preview: str = ""  # message[:500]
    message_uuid: str | None = None
    chat_uuid: str | None = None
    sender_user_id: int | None = None
    recipient_user_id: int | None = None


@dataclass
class Params:
    message: str = ""
    suggested_action: str = "reply"
    slack_message: str = ""
    slack_thread: str = ""
    scheduled_at: str = ""
    note: str = ""


def _mark_source_message_read(static_params: dict) -> None:
    from chat.models import Message

    message_uuid = static_params.get("message_uuid")
    if not message_uuid:
        raise ValueError("mark_read requires message_uuid in static_parameters.")
    source_message = Message.objects.filter(uuid=message_uuid).first()
    if source_message is None:
        raise ValueError(f"mark_read could not find message '{message_uuid}'.")
    if not source_message.read:
        source_message.read = True
        source_message.save(update_fields=["read"])


@register("support_reply", static_schema=StaticParams, param_schema=Params)
def support_reply(static_params: dict, params: dict) -> None:
    """Send the admin's reply to a user's support (help) message.

    static_params:
        help_message_id (int): ID of the originating HelpMessage

    params:
        message (str): The reply text to send to the user
        suggested_action (str): One of "reply" (default), "mark_read", "slack_feedback", "keep_open"
        slack_message (str): Text to post when suggested_action == "slack_feedback"
        slack_thread (str): Named Slack thread key when suggested_action == "slack_feedback"
    """
    suggested_action = (params.get("suggested_action") or "reply").strip()

    if suggested_action == "mark_read":
        _mark_source_message_read(static_params)
        return

    if suggested_action == "slack_feedback":
        from management.api.slack import post_support_feedback_to_slack

        text = (params.get("slack_message") or params.get("message") or "").strip()
        if not text:
            raise ValueError("slack_feedback requires a non-empty slack_message.")
        thread_key = (params.get("slack_thread") or "").strip()
        post_support_feedback_to_slack(text, thread_key)
        return

    if suggested_action == "keep_open":
        # Handled by the dedicated keep-open endpoint; a generic execute is a no-op
        # so the action is never accidentally completed as a reply.
        return

    from chat.models import Message

    from management.controller import get_base_management_user
    from management.models.help_message import HelpMessage

    management_user = get_base_management_user()

    message_uuid = static_params.get("message_uuid")
    if message_uuid:
        source_message = Message.objects.filter(uuid=message_uuid).select_related("sender").first()
        if source_message is not None:
            source_message.sender.message(params["message"], sender=management_user, apply_delivery_side_effects=True)
            return

    help_message_id = static_params.get("help_message_id")
    if help_message_id is None:
        raise ValueError("support_reply requires either message_uuid or help_message_id in static_parameters.")

    help_message = HelpMessage.objects.get(id=help_message_id)
    help_message.user.message(params["message"], sender=management_user, apply_delivery_side_effects=True)


register_task_type(
    "support_reply",
    action_type="support_reply",
    task_title=lambda s: f"Support request ({s['kind_display']})",
    task_description=lambda s: s["message_preview"],
)
