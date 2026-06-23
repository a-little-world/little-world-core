import base64
import json
import logging
from importlib import import_module
from urllib.parse import urlparse, urlunparse

from celery import current_app, shared_task
from chat.models import Chat
from chat.models import Message as ChatMessage
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.db.models import Q
from requests import RequestException

from management import controller
from management.models.open_chat_configuration import OpenChatConfiguration
from management.models.support_task import SupportTask, SupportTaskAction
from management.models.user import User
from management.permissions import ManagementPermission

logger = logging.getLogger(__name__)


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


def _normalize_base_url_for_open_chat_tool(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.hostname != "localhost":
        return base_url

    port = f":{parsed.port}" if parsed.port else ""
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"

    normalized_netloc = f"{userinfo}host.docker.internal{port}"
    return urlunparse(parsed._replace(netloc=normalized_netloc))


def _apply_bot_config_overwrite(bot_config: dict, overwrite: object) -> dict:
    if not isinstance(overwrite, dict):
        return bot_config

    merged = bot_config.copy()
    for key, value in overwrite.items():
        if key in merged:
            merged[key] = value
    return merged


def _extract_interaction_rows(payload: object) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("rows", "results", "items", "interactions", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return candidate
    return []


def _build_default_bot_config(
    *,
    tools: list[str] | None = None,
    system_prompt: str | None = None,
) -> dict:
    resolved_tools = ["little_world__chat_reply"] if tools is None else tools
    resolved_system_prompt = (
        "You are a Little World support assistant. "
        "Always send your final response by calling `little_world__chat_reply`."
        if system_prompt is None
        else system_prompt
    )
    return {
        "temperature": 0.0,
        "max_tokens": 1024,
        "tools": resolved_tools,
        "model": "qwen3-8b-instruct_vllm",
        "endpoint": "https://litellm.t1m.me/v1",
        "backend": "litellm",
        "context": 2000,
        "system_prompt": resolved_system_prompt,
    }


def _run_open_chat_interaction_flow(
    *,
    configuration: OpenChatConfiguration,
    recipient: User,
    sender: User,
    chat_uuid: str,
    message_uuid: str,
    user_message_text: str,
    config_owner: str,
    use_little_world_reply_tool: bool = True,
    create_chat_interaction_message: bool = True,
) -> dict:
    try:
        from client.client import OpenChatPythonClient
    except ImportError as exc:
        return {"status": "error", "reason": "open_chat_client_import_failed", "detail": str(exc)}

    tools = ["little_world__chat_reply"] if use_little_world_reply_tool else []
    system_prompt = (
        "You are a Little World support assistant. "
        "Always send your final response by calling `little_world__chat_reply`."
        if use_little_world_reply_tool
        else ("You are a support assistant. Respond naturally without using any external reply tools.")
    )
    bot_config = _apply_bot_config_overwrite(
        _build_default_bot_config(
            tools=tools,
            system_prompt=system_prompt,
        ),
        configuration.interaction_overwrite,
    )
    tool_init = None
    if use_little_world_reply_tool:
        session_id, csrf_token = _create_session_and_csrf_for_user(recipient)
        tool_init = _build_little_world_tool_init(
            session_id=session_id,
            csrf_token=csrf_token,
            api_host=_normalize_base_url_for_open_chat_tool(settings.BASE_URL),
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

        interaction_message = (
            _build_little_world_instruction(user_message_text)
            if use_little_world_reply_tool
            else ((user_message_text or "").strip() or "Hello")
        )
        if tool_init is not None:
            interaction = client.create_interaction(
                tool_init=tool_init,
                message=interaction_message,
            )
        else:
            interaction = client.create_interaction(message=interaction_message)
        interaction_uuid = interaction.get("uuid") if isinstance(interaction, dict) else None
        logger.info(
            "open_chat_interaction_flow login_user=%s config_owner=%s interaction_uuid=%s",
            login_result.get("name") if isinstance(login_result, dict) else None,
            config_owner,
            interaction_uuid,
        )

        interaction_single_page_count = None
        interaction_total_pages = None
        interaction_merged_count = None
        interaction_present_in_merged = None

        get_interactions = getattr(client, "get_interactions", None)
        if callable(get_interactions):
            try:
                single_page_payload = get_interactions(page=1, limit=40, all_pages=False)
                merged_payload = get_interactions(page=1, limit=40)
            except TypeError:
                single_page_payload = get_interactions(page=1, limit=40)
                merged_payload = get_interactions()

            single_rows = _extract_interaction_rows(single_page_payload)
            merged_rows = _extract_interaction_rows(merged_payload)
            interaction_single_page_count = len(single_rows)
            interaction_merged_count = len(merged_rows)
            if isinstance(single_page_payload, dict):
                interaction_total_pages = single_page_payload.get("total_pages")
            if interaction_uuid:
                interaction_present_in_merged = any(
                    isinstance(row, dict)
                    and str(
                        row.get("interaction_id") or row.get("uuid") or row.get("id") or row.get("interaction_uuid")
                    )
                    == str(interaction_uuid)
                    for row in merged_rows
                )
                if interaction_present_in_merged is False:
                    return {
                        "status": "error",
                        "reason": "created_interaction_missing_from_get_interactions",
                        "interaction_uuid": interaction_uuid,
                        "single_page_count": interaction_single_page_count,
                        "total_pages": interaction_total_pages,
                        "merged_count": interaction_merged_count,
                    }

        shared_url = None
        tool_called = False
        if interaction_uuid:
            get_shared_url = getattr(client, "get_shared_interaction_url", None)
            if callable(get_shared_url):
                shared_url = get_shared_url(interaction_uuid)
            if use_little_world_reply_tool:
                list_messages = getattr(client, "list_interaction_messages", None)
                interaction_messages_payload = None
                if callable(list_messages):
                    try:
                        interaction_messages_payload = list_messages(interaction_uuid, page=1, limit=200)
                    except TypeError:
                        interaction_messages_payload = list_messages(interaction_uuid)
                else:
                    get_messages = getattr(client, "get_interaction_messages", None)
                    if callable(get_messages):
                        try:
                            interaction_messages_payload = get_messages(interaction_uuid, wait_seconds=5)
                        except TypeError:
                            interaction_messages_payload = get_messages(interaction_uuid)

                interaction_messages = _extract_interaction_rows(interaction_messages_payload)
                for item in interaction_messages:
                    if not isinstance(item, dict):
                        continue
                    tool_calls = item.get("tool_calls")
                    if not isinstance(tool_calls, list):
                        continue
                    if any(isinstance(tc, dict) and tc.get("name") == "little_world__chat_reply" for tc in tool_calls):
                        tool_called = True
                        break

        interaction_message_uuid = None
        interaction_message_payload = None
        if interaction_uuid and create_chat_interaction_message:
            from chat.consumers.messages import NewMessage
            from chat.models import ChatSerializer, MessageSerializer

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
                interaction_message = ChatMessage.objects.create(
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
            "sender_uuid": str(sender.uuid),
            "recipient_uuid": str(recipient.uuid),
            "recipient_user_id": recipient.pk,
            "configuration_owner": config_owner,
            "configuration_user_id": configuration.user.pk,
            "login_user_name": login_result.get("name") if isinstance(login_result, dict) else None,
            "interaction_message_input": user_message_text,
            "interaction_uuid": interaction_uuid,
            "shared_url": shared_url,
            "tool_called": tool_called,
            "interaction_single_page_count": interaction_single_page_count,
            "interaction_total_pages": interaction_total_pages,
            "interaction_merged_count": interaction_merged_count,
            "interaction_present_in_merged": interaction_present_in_merged,
            "interaction_message_uuid": interaction_message_uuid,
            "interaction_message_payload": interaction_message_payload,
        }
    except RequestException as exc:
        return {"status": "error", "reason": "open_chat_request_failed", "detail": str(exc)}
    except Exception as exc:
        return {"status": "error", "reason": "open_chat_basic_interaction_failed", "detail": str(exc)}


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

    recipient_configuration = OpenChatConfiguration.objects.filter(user_id=recipient.pk).first()
    configuration = recipient_configuration
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
    return _run_open_chat_interaction_flow(
        configuration=configuration,
        recipient=recipient,
        sender=sender,
        chat_uuid=chat_uuid,
        message_uuid=message_uuid,
        user_message_text=user_message_text,
        config_owner=config_owner,
    )


@shared_task(name="management.tasks.idempotent_actions__generate_message_replies")
def idempotent_actions__generate_message_replies(
    target_user_uuid: str,
    triggered_by_user_uuid: str | None = None,
):
    target_user = User.objects.filter(uuid=target_user_uuid).first()
    if target_user is None:
        return {"status": "skipped", "reason": "target_user_missing", "target_user_uuid": target_user_uuid}
    if not target_user.has_perm(ManagementPermission.OPEN_CHAT_ACCESS):
        return {
            "status": "skipped",
            "reason": "target_user_has_no_open_chat_access_permission",
            "target_user_uuid": target_user_uuid,
        }

    configuration = OpenChatConfiguration.objects.filter(user_id=target_user.pk).first()
    if configuration is None:
        return {
            "status": "skipped",
            "reason": "target_user_open_chat_configuration_missing",
            "target_user_uuid": target_user_uuid,
        }

    automation_user_email = (getattr(settings, "OPEN_CHAT_AUTOMATION_USER_EMAIL", "") or "").strip()
    created_by_user = User.objects.filter(email=automation_user_email).first() if automation_user_email else None
    if created_by_user is None:
        created_by_user = controller.create_open_chat_automation_user()
    if created_by_user is None:
        return {
            "status": "skipped",
            "reason": "open_chat_automation_user_missing",
            "target_user_uuid": target_user_uuid,
        }
    assigned_to_user = controller.get_base_management_user()

    from management.api.user_advanced_filter import (
        get_user_with_message_to_admin_that_are_read_or_not_read_but_not_replied,
    )

    pending_users = list(get_user_with_message_to_admin_that_are_read_or_not_read_but_not_replied(User.objects.all()))
    processed_messages: list[dict] = []
    created_tasks = 0
    enqueued_interactions = 0

    for source_user in pending_users:
        if source_user.has_perm(ManagementPermission.MATCHING_USER):
            processed_messages.append(
                {
                    "source_user_uuid": str(source_user.uuid),
                    "status": "skipped_matching_user_permission",
                }
            )
            continue

        latest_message = (
            ChatMessage.objects.filter(
                Q(sender_id=source_user.pk, recipient_id=target_user.pk)
                | Q(sender_id=target_user.pk, recipient_id=source_user.pk)
            )
            .order_by("-created", "-id")
            .first()
        )
        if latest_message is None or latest_message.sender.pk != source_user.pk:
            continue

        existing_action = (
            SupportTaskAction.objects.select_related("task")
            .filter(
                action_type="support_reply",
                status=SupportTaskAction.Status.OPEN,
                task__status__in=[SupportTask.Status.NEW, SupportTask.Status.IN_PROGRESS],
                static_parameters__message_uuid=str(latest_message.uuid),
            )
            .first()
        )
        if existing_action is not None:
            processed_messages.append(
                {
                    "message_uuid": str(latest_message.uuid),
                    "chat_uuid": str(latest_message.chat.uuid),
                    "support_task_id": existing_action.task.pk,
                    "status": "skipped_duplicate",
                }
            )
            continue

        support_task = SupportTask.create_of_type(
            "support_reply",
            static_parameters={
                "help_message_id": None,
                "kind_display": "Open Chat",
                "message_preview": latest_message.text[:500],
                "message_uuid": str(latest_message.uuid),
                "chat_uuid": str(latest_message.chat.uuid),
                "sender_user_id": source_user.pk,
                "recipient_user_id": target_user.pk,
            },
            parameters={"message": ""},
            created_by=created_by_user,
            assigned_to=assigned_to_user,
            related_user=source_user,
        )
        created_tasks += 1
        interaction_task = current_app.send_task(  # pyright: ignore[reportCallIssue]
            "management.tasks.open_chat_trigger_interaction",
            kwargs={
                "configuration_user_uuid": str(configuration.user.uuid),
                "chat_uuid": str(latest_message.chat.uuid),
                "message_uuid": str(latest_message.uuid),
                "sender_uuid": str(source_user.uuid),
                "recipient_uuid": str(target_user.uuid),
                "user_message_text": latest_message.text or "",
                "support_task_id": support_task.pk,
                "use_little_world_reply_tool": False,
                "create_chat_interaction_message": False,
            },
        )
        enqueued_interactions += 1
        processed_messages.append(
            {
                "message_uuid": str(latest_message.uuid),
                "chat_uuid": str(latest_message.chat.uuid),
                "support_task_id": support_task.pk,
                "interaction_task_id": interaction_task.id,
                "status": "created_and_enqueued",
            }
        )

    return {
        "status": "ok",
        "trigger": "idempotent_actions__generate_message_replies",
        "target_user_uuid": target_user_uuid,
        "triggered_by_user_uuid": triggered_by_user_uuid,
        "created_tasks_count": created_tasks,
        "enqueued_interactions_count": enqueued_interactions,
        "processed_messages": processed_messages,
    }


@shared_task(name="management.tasks.open_chat_trigger_interaction")
def open_chat_trigger_interaction(
    configuration_user_uuid: str,
    chat_uuid: str,
    message_uuid: str,
    sender_uuid: str,
    recipient_uuid: str,
    user_message_text: str = "",
    support_task_id: int | None = None,
    use_little_world_reply_tool: bool = True,
    create_chat_interaction_message: bool = True,
):
    configuration_user = User.objects.filter(uuid=configuration_user_uuid).first()
    if configuration_user is None:
        return {
            "status": "skipped",
            "reason": "configuration_user_missing",
            "configuration_user_uuid": configuration_user_uuid,
        }
    configuration = OpenChatConfiguration.objects.filter(user_id=configuration_user.pk).first()
    if configuration is None:
        return {
            "status": "skipped",
            "reason": "configuration_missing",
            "configuration_user_uuid": configuration_user_uuid,
        }

    sender = User.objects.filter(uuid=sender_uuid).first()
    if sender is None:
        return {"status": "skipped", "reason": "sender_missing", "sender_uuid": sender_uuid}
    recipient = User.objects.filter(uuid=recipient_uuid).first()
    if recipient is None:
        return {"status": "skipped", "reason": "recipient_missing", "recipient_uuid": recipient_uuid}
    if not recipient.has_perm(ManagementPermission.OPEN_CHAT_ACCESS):
        return {"status": "skipped", "reason": "recipient_has_no_open_chat_access_permission"}

    result = _run_open_chat_interaction_flow(
        configuration=configuration,
        recipient=recipient,
        sender=sender,
        chat_uuid=chat_uuid,
        message_uuid=message_uuid,
        user_message_text=user_message_text,
        config_owner="explicit_configuration_user",
        use_little_world_reply_tool=use_little_world_reply_tool,
        create_chat_interaction_message=create_chat_interaction_message,
    )
    if support_task_id and result.get("status") == "ok" and result.get("interaction_uuid"):
        support_action = SupportTaskAction.objects.filter(task_id=support_task_id).first()
        if support_action is not None:
            static_parameters = dict(support_action.static_parameters or {})
            static_parameters["interaction_id"] = str(result.get("interaction_uuid"))
            static_parameters["shared_interaction_url"] = result.get("shared_url")
            support_action.static_parameters = static_parameters
            support_action.save(update_fields=["static_parameters"])
    return result
