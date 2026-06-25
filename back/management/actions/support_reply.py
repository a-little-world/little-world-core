from dataclasses import dataclass

from .registry import register, register_task_type


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
    message: str


@register("support_reply", static_schema=StaticParams, param_schema=Params)
def support_reply(static_params: dict, params: dict) -> None:
    """Send the admin's reply to a user's support (help) message.

    static_params:
        help_message_id (int): ID of the originating HelpMessage

    params:
        message (str): The reply text to send to the user
    """
    from chat.models import Message

    from management.controller import get_base_management_user
    from management.models.help_message import HelpMessage

    management_user = get_base_management_user()

    message_uuid = static_params.get("message_uuid")
    if message_uuid:
        source_message = Message.objects.filter(uuid=message_uuid).select_related("sender").first()
        if source_message is not None:
            source_message.sender.message(params["message"], sender=management_user)
            return

    help_message_id = static_params.get("help_message_id")
    if help_message_id is None:
        raise ValueError("support_reply requires either message_uuid or help_message_id in static_parameters.")

    help_message = HelpMessage.objects.get(id=help_message_id)
    help_message.user.message(params["message"], sender=management_user)


register_task_type(
    "support_reply",
    action_type="support_reply",
    task_title=lambda s: f"Support request ({s['kind_display']})",
    task_description=lambda s: s["message_preview"],
)
