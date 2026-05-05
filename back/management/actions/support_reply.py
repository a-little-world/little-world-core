from .registry import register


@register("send_support_reply")
def send_support_reply(static_params: dict, params: dict) -> None:
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
