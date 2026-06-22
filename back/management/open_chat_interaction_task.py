import base64
import json
from importlib import import_module

from celery import shared_task
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.conf import settings
from requests import RequestException

from management.models.open_chat_configuration import OpenChatConfiguration
from management.models.user import User
from management.permissions import ManagementPermission


def _build_little_world_tool_init(*, session_id: str, csrf_token: str, api_host: str, lw_chat_uuid: str) -> dict:
    return {
        "little_world__chat_reply": {
            "session_id": session_id,
            "csrf_token": csrf_token,
            "api_host": api_host.rstrip("/"),
            "chat_uuid": lw_chat_uuid,
        }
    }


def _build_little_world_instruction(user_message_text: str) -> str:
    incoming = (user_message_text or "").strip() or "Hello"
    return (
        "You are handling a Little World support conversation. "
        "Generate a helpful support reply and call tool `little_world__chat_reply` exactly once "
        "with the final outbound message in parameter `message`. "
        "Do not ask for confirmation. "
        f"Incoming user message: {incoming}"
    )


def _create_session_and_csrf_for_user(user: User) -> tuple[str, str]:
    from django.middleware.csrf import _get_new_csrf_string

    session_engine = import_module(settings.SESSION_ENGINE)
    session = session_engine.SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    return session.session_key, _get_new_csrf_string()


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
    2) ensure recipient has OpenChatConfiguration
    3) login with Open Chat client using recipient configuration
    4) run a basic interaction flow
    """
    recipient = User.objects.filter(uuid=recipient_uuid).first()
    if recipient is None:
        return {"status": "skipped", "reason": "recipient_missing"}

    sender = User.objects.filter(uuid=sender_uuid).first()
    if sender is None:
        return {"status": "skipped", "reason": "sender_missing"}

    if not recipient.has_perm(ManagementPermission.OPEN_CHAT_ACCESS):
        return {"status": "skipped", "reason": "recipient_has_no_open_chat_access_permission"}

    try:
        from client.client import OpenChatPythonClient
    except ImportError as exc:
        return {"status": "error", "reason": "open_chat_client_import_failed", "detail": str(exc)}

    bot_config = {
        "temperature": 0.0,
        "max_tokens": 1024,
        "tools": ["little_world__chat_reply"],
        "model": "qwen3-8b-instruct_vllm",
        "endpoint": "https://litellm.t1m.me/v1",
        "backend": "litellm",
        "context": 10,
        "system_prompt": (
            "You are a Little World support assistant. "
            "Always send your final response by calling `little_world__chat_reply`."
        ),
    }

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

    session_id, csrf_token = _create_session_and_csrf_for_user(recipient)
    tool_init = _build_little_world_tool_init(
        session_id=session_id,
        csrf_token=csrf_token,
        api_host=settings.BASE_URL,
        lw_chat_uuid=chat_uuid,
    )

    try:
        client = OpenChatPythonClient(
            host=configuration.open_chat_host,
            username=configuration.open_chat_user,
            password=configuration.open_chat_api_key,
        )
        client.setup_bot_config(bot_config)
        login_result = client.login()

        interaction = client.create_interaction(
            tool_init=tool_init,
            message=_build_little_world_instruction(user_message_text),
        )
        interaction_uuid = interaction.get("uuid") if isinstance(interaction, dict) else None
        shared_url = None
        tool_called = False
        if interaction_uuid:
            get_shared_url = getattr(client, "get_shared_interaction_url", None)
            if callable(get_shared_url):
                shared_url = get_shared_url(interaction_uuid)
            get_messages = getattr(client, "get_interaction_messages", None)
            if callable(get_messages):
                interaction_messages = get_messages(interaction_uuid, wait_seconds=5)
                if isinstance(interaction_messages, list):
                    for item in interaction_messages:
                        if not isinstance(item, dict):
                            continue
                        tool_calls = item.get("tool_calls")
                        if not isinstance(tool_calls, list):
                            continue
                        if any(
                            isinstance(tc, dict) and tc.get("name") == "little_world__chat_reply" for tc in tool_calls
                        ):
                            tool_called = True
                            break

        interaction_message_uuid = None
        interaction_message_payload = None
        if interaction_uuid:
            from chat.consumers.messages import NewMessage
            from chat.models import Chat, ChatSerializer, Message, MessageSerializer

            chat = Chat.objects.filter(uuid=chat_uuid).first()
            if chat is not None and chat.is_participant(sender) and chat.is_participant(recipient):
                interaction_message_payload = {
                    "type": "open_chat_interaction",
                    "title": base64.b64decode(
                        "VGltOiBUaGlzIGlzICpoaWdobHkqIGV4cGVyaW1lbnRhbDsgdGhlIG1vZGVsIHJ1bnMgYXQgaG9tZSBvbiBteSBwYyBhbmQgbWlnaCB3YWtlIHdlIHVwIGF0IG5pZ2h0OyBidXQgbWF5YmUgaXQgY2FuIGhlbHAgeW91IHdpdGggc29tZXRoaW5nLg=="
                    ).decode("utf-8"),
                    "interaction_id": interaction_uuid,
                    "shared_interaction_url": shared_url,
                }
                interaction_message = Message.objects.create(
                    chat=chat,
                    sender=recipient,
                    recipient=sender,
                    recipient_notified=False,
                    text=json.dumps(interaction_message_payload),
                    parsable_message=True,
                )
                interaction_message_uuid = str(interaction_message.uuid)
                serialized_interaction_message = MessageSerializer(interaction_message).data
                NewMessage(
                    message=serialized_interaction_message,
                    chat_id=str(chat.uuid),
                    meta_chat_obj=ChatSerializer(chat, context={"user": sender}).data,
                ).send(str(sender.uuid))

        return {
            "status": "ok",
            "chat_uuid": chat_uuid,
            "message_uuid": message_uuid,
            "sender_uuid": sender_uuid,
            "recipient_uuid": recipient_uuid,
            "recipient_user_id": recipient.pk,
            "configuration_owner": config_owner,
            "configuration_user_id": configuration.user.pk,
            "login_user_name": login_result.get("name") if isinstance(login_result, dict) else None,
            "interaction_message_input": user_message_text,
            "interaction_uuid": interaction_uuid,
            "shared_url": shared_url,
            "tool_called": tool_called,
            "interaction_message_uuid": interaction_message_uuid,
            "interaction_message_payload": interaction_message_payload,
        }
    except RequestException as exc:
        return {"status": "error", "reason": "open_chat_request_failed", "detail": str(exc)}
    except Exception as exc:
        return {"status": "error", "reason": "open_chat_basic_interaction_failed", "detail": str(exc)}
