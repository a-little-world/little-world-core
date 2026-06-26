import json
import logging

from celery import shared_task
from chat.models import Chat
from chat.models import Message as ChatMessage
from client.client import OpenChatPythonClient

from management.helpers.open_chat import (
    FALLBACK_USER_MESSAGE,
    _apply_bot_config_overwrite,
    build_default_bot_config,
    build_tool_session_context,
    detect_expected_tool_call,
    value_or,
)
from management.models.open_chat_configuration import OpenChatConfiguration
from management.models.user import User
from management.permissions import ManagementPermission

logger = logging.getLogger(__name__)

CHAT_REPLY_TOOL = "little_world__chat_reply"

SYSTEM_PROMPT_CHAT_REPLY = """
Du bist ein Little-World-Support-Assistent.
Gib die finale Antwort immer aus, indem du genau einmal das Tool `little_world__chat_reply` aufrufst.
""".strip()


def _publish_interaction_chat_message(
    *,
    chat_uuid: str,
    sender: User,
    recipient: User,
    interaction_uuid: str,
    shared_url: str,
) -> tuple[str | None, dict | None]:
    from chat.consumers.messages import NewMessage
    from chat.models import ChatSerializer, MessageSerializer

    chat = Chat.objects.filter(uuid=chat_uuid).first()
    if chat is None or not chat.is_participant(sender) or not chat.is_participant(recipient):
        return None, None

    payload = {
        "type": "open_chat_interaction",
        "title": "Tim: Very early experimental Open-Chat integration, use with caution",
        "interaction_id": interaction_uuid,
        "shared_interaction_url": shared_url,
    }
    message = ChatMessage.objects.create(
        chat=chat,
        sender=recipient,
        recipient=sender,
        recipient_notified=False,
        text=json.dumps(payload),
        parsable_message=True,
    )
    NewMessage(
        message=MessageSerializer(message).data,
        chat_id=str(chat.uuid),
        meta_chat_obj=ChatSerializer(chat, context={"user": sender}).data,
    ).send(str(sender.uuid))
    return str(message.uuid), payload


@shared_task(name="management.tasks.open_chat_basic_chat_interaction")
def open_chat_basic_chat_interaction(
    chat_uuid: str,
    message_uuid: str,
    sender_uuid: str,
    recipient_uuid: str,
    user_message_text: str = "",
):
    """
    Basic Open Chat interaction for messages sent to Open Chat recipients.
    Flow:
    1) ensure recipient exists and has OPEN_CHAT_ACCESS permission
    2) resolve the recipient's OpenChatConfiguration (falling back to the sender's)
    3) run a chat-reply interaction and publish the result back into the chat
    """
    recipient = User.objects.filter(uuid=recipient_uuid).first()
    if recipient is None:
        return {"status": "skipped", "reason": "recipient_missing"}

    sender = User.objects.filter(uuid=sender_uuid).first()
    if sender is None:
        return {"status": "skipped", "reason": "sender_missing"}

    if not recipient.has_perm(ManagementPermission.OPEN_CHAT_ACCESS):
        return {"status": "skipped", "reason": "recipient_has_no_open_chat_access_permission"}

    configuration = OpenChatConfiguration.objects.filter(user_id=recipient.pk).first()
    config_owner = "recipient"
    if configuration is None:
        sender_has_open_chat_access = sender.has_perm(ManagementPermission.OPEN_CHAT_ACCESS)
        sender_configuration = OpenChatConfiguration.objects.filter(user_id=sender.pk).first()
        if sender_has_open_chat_access and sender_configuration is not None:
            configuration = sender_configuration
            config_owner = "sender_fallback"
        else:
            return {
                "status": "skipped",
                "reason": "recipient_open_chat_configuration_missing",
                "recipient_user_id": recipient.pk,
                "recipient_email": recipient.email,
                "sender_user_id": sender.pk,
                "sender_email": sender.email,
                "sender_has_open_chat_access": sender_has_open_chat_access,
                "sender_has_open_chat_configuration": sender_configuration is not None,
            }

    bot_config = _apply_bot_config_overwrite(
        build_default_bot_config(tools=[CHAT_REPLY_TOOL], system_prompt=SYSTEM_PROMPT_CHAT_REPLY),
        configuration.interaction_overwrite,
    )
    # Never allow per-user interaction_overwrite to disable the selected runtime tool mode.
    bot_config["tools"] = [CHAT_REPLY_TOOL]
    bot_config["system_prompt"] = SYSTEM_PROMPT_CHAT_REPLY

    session_id, csrf_token, api_host = build_tool_session_context(recipient)
    tool_init = {
        CHAT_REPLY_TOOL: {
            "session_id": session_id,
            "csrf_token": csrf_token,
            "api_host": api_host,
            "chat_uuid": chat_uuid,
        }
    }

    try:
        client = OpenChatPythonClient(
            host=configuration.open_chat_host,
            username=configuration.open_chat_user,
            password=configuration.open_chat_api_key,
        )
        client.setup_bot_config(bot_config)
        login_user = client.login()

        message = (user_message_text or "").strip() or FALLBACK_USER_MESSAGE
        interaction = client.create_interaction(tool_init=tool_init, message=message)
        interaction_uuid = value_or(interaction.uuid, "")
        if not interaction_uuid:
            return {"status": "error", "reason": "created_interaction_missing_uuid"}

        login_user_name = value_or(login_user.name, "")
        logger.info(
            "open_chat_basic_chat_interaction login_user=%s config_owner=%s interaction_uuid=%s",
            login_user_name,
            config_owner,
            interaction_uuid,
        )

        shared_url = client.get_shared_interaction_url(interaction_uuid)
        tool_called = detect_expected_tool_call(client, interaction_uuid, {CHAT_REPLY_TOOL})
        interaction_message_uuid, interaction_message_payload = _publish_interaction_chat_message(
            chat_uuid=chat_uuid,
            sender=sender,
            recipient=recipient,
            interaction_uuid=interaction_uuid,
            shared_url=shared_url,
        )

        return {
            "status": "ok",
            "chat_uuid": chat_uuid,
            "message_uuid": message_uuid,
            "sender_uuid": str(sender.uuid),
            "recipient_uuid": str(recipient.uuid),
            "configuration_owner": config_owner,
            "configuration_user_id": configuration.user.pk,
            "login_user_name": login_user_name,
            "interaction_uuid": interaction_uuid,
            "shared_url": shared_url,
            "tool_called": tool_called,
            "interaction_message_uuid": interaction_message_uuid,
            "interaction_message_payload": interaction_message_payload,
        }
    except Exception as exc:
        return {"status": "error", "reason": "open_chat_interaction_failed", "detail": str(exc)}
