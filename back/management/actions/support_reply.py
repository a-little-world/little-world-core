from dataclasses import dataclass

from .registry import register, register_task_type


@dataclass
class StaticParams:
    help_message_id: int
    kind_display: str  # e.g. "General", "Technical"
    message_preview: str  # message[:500]


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
    from management.controller import get_base_management_user
    from management.models.help_message import HelpMessage

    help_message = HelpMessage.objects.get(id=static_params["help_message_id"])
    management_user = get_base_management_user()
    management_user.message(help_message.user, params["message"])


register_task_type(
    "support_reply",
    action_type="support_reply",
    task_title=lambda s: f"Support request ({s['kind_display']})",
    task_description=lambda s: s["message_preview"],
)
