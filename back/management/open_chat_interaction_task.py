import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from urllib.parse import urlparse, urlunparse

from celery import current_app, shared_task
from chat.models import Chat
from chat.models import Message as ChatMessage
from client.client import OpenChatPythonClient
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


def _get_tool_call_name(tool_call) -> str:
    try:
        return tool_call.name
    except Exception:
        return tool_call["name"]


class OpenChatInteractionToolMode(StrEnum):
    CHAT_REPLY = "chat_reply"
    MESSAGE_REPLY_SUGGESTION = "message_reply_suggestion"
    NO_TOOLS = "no_tools"


FALLBACK_USER_MESSAGE = "Hallo"

SYSTEM_PROMPT_CHAT_REPLY = """
Du bist ein Little-World-Support-Assistent.
Gib die finale Antwort immer aus, indem du genau einmal das Tool `little_world__chat_reply` aufrufst.
""".strip()

SYSTEM_PROMPT_MESSAGE_REPLY_SUGGESTION = """
Du bearbeitest eine Little-World-Support-Konversation.
Erstelle eine kurze und hilfreiche finale Antwort auf die letzte Nutzernachricht.
Rufe genau einmal das Tool `little_world__generate_message_reply_suggestion` auf, um den Entwurf zu speichern.
Stelle niemals Rueckfragen und bitte niemals um mehr Informationen.
Wenn die Eingabe unklar oder sehr kurz ist, erstelle trotzdem einen bestmoeglichen, freundlichen Antwortentwurf.
Frage nicht nach einer Bestaetigung und rufe keine anderen Tools auf.
Uebergib als Argument nur den Entwurfstext in `message`.
""".strip()

SYSTEM_PROMPT_NO_TOOLS = """
Du bist ein Support-Assistent.
Antworte natuerlich, ohne externe Tools zu verwenden.
""".strip()


def _build_little_world_tool_init(
    *,
    session_id: str,
    csrf_token: str,
    api_host: str,
    lw_chat_uuid: str | None = None,
    support_task_pk: int | None = None,
    support_task_action_id: str | None = None,
) -> dict:
    normalized_api_host = api_host.rstrip("/")
    tool_init: dict[str, dict[str, str | int]] = {}
    if lw_chat_uuid is not None:
        tool_init["little_world__chat_reply"] = {
            "session_id": session_id,
            "csrf_token": csrf_token,
            "api_host": normalized_api_host,
            "chat_uuid": lw_chat_uuid,
        }
    if support_task_pk is not None and support_task_action_id is not None:
        tool_init["little_world__generate_message_reply_suggestion"] = {
            "session_id": session_id,
            "csrf_token": csrf_token,
            "api_host": normalized_api_host,
            "task_pk": str(support_task_pk),
            "action_id": support_task_action_id,
        }
    return tool_init


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


def resolve_open_chat_automation_task_creator_user() -> User | None:
    automation_user_email = (settings.OPEN_CHAT_AUTOMATION_USER_EMAIL or "").strip()
    created_by_user = User.objects.filter(email=automation_user_email).first() if automation_user_email else None
    if created_by_user is None:
        created_by_user = controller.create_open_chat_automation_user()
    return created_by_user


def create_or_reuse_support_reply_task_for_message(
    *,
    latest_message: ChatMessage,
    source_user: User,
    target_user: User,
    created_by_user: User,
    assigned_to_user: User,
    configuration_user_uuid: str | None = None,
    enqueue_interaction: bool = True,
) -> dict:
    if source_user.has_perm(ManagementPermission.MATCHING_USER):
        return {
            "source_user_uuid": str(source_user.uuid),
            "status": "skipped_matching_user_permission",
        }

    if latest_message.sender.pk != source_user.pk:
        return {
            "message_uuid": str(latest_message.uuid),
            "chat_uuid": str(latest_message.chat.uuid),
            "status": "skipped_not_source_user_message",
        }

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
        if existing_action.task.assigned_to is None:
            SupportTask.objects.filter(pk=existing_action.task.pk).update(assigned_to_id=assigned_to_user.pk)
        return {
            "message_uuid": str(latest_message.uuid),
            "chat_uuid": str(latest_message.chat.uuid),
            "support_task_id": existing_action.task.pk,
            "status": "skipped_duplicate",
        }

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
    if support_task.assigned_to is None:
        SupportTask.objects.filter(pk=support_task.pk).update(assigned_to_id=assigned_to_user.pk)

    result = {
        "message_uuid": str(latest_message.uuid),
        "chat_uuid": str(latest_message.chat.uuid),
        "support_task_id": support_task.pk,
        "status": "created",
    }
    if not enqueue_interaction or not configuration_user_uuid:
        return result

    interaction_task = current_app.send_task(  # pyright: ignore[reportCallIssue]
        "management.tasks.open_chat_trigger_interaction",
        kwargs={
            "configuration_user_uuid": configuration_user_uuid,
            "chat_uuid": str(latest_message.chat.uuid),
            "message_uuid": str(latest_message.uuid),
            "sender_uuid": str(source_user.uuid),
            "recipient_uuid": str(target_user.uuid),
            "user_message_text": latest_message.text or "",
            "support_task_id": support_task.pk,
            "tool_mode": OpenChatInteractionToolMode.MESSAGE_REPLY_SUGGESTION.value,
            "publish_chat_interaction_message": False,
        },
    )
    result["interaction_task_id"] = interaction_task.id
    result["status"] = "created_and_enqueued"
    return result


def _build_default_bot_config(
    *,
    tools: list[str] | None = None,
    system_prompt: str | None = None,
) -> dict:
    resolved_tools = ["little_world__chat_reply"] if tools is None else tools
    resolved_system_prompt = SYSTEM_PROMPT_CHAT_REPLY if system_prompt is None else system_prompt
    return {
        "temperature": 0.0,
        "max_tokens": 8000,
        "tools": resolved_tools,
        "model": "qwen3-8b-instruct_vllm",
        "endpoint": "https://litellm.t1m.me/v1",
        "backend": "litellm",
        "context": 8000,
        "system_prompt": resolved_system_prompt,
    }


@dataclass(frozen=True)
class _PreparedInteractionFlow:
    bot_config: dict
    tool_init: dict | None
    expected_tool_names: set[str]


def _prepare_chat_reply_flow(
    *,
    configuration: OpenChatConfiguration,
    recipient: User,
    chat_uuid: str,
    tool_init_user: User | None,
) -> _PreparedInteractionFlow:
    bot_config = _apply_bot_config_overwrite(
        _build_default_bot_config(
            tools=["little_world__chat_reply"],
            system_prompt=SYSTEM_PROMPT_CHAT_REPLY,
        ),
        configuration.interaction_overwrite,
    )
    # Never allow per-user interaction_overwrite to disable the selected runtime tool mode.
    bot_config["tools"] = ["little_world__chat_reply"]
    bot_config["system_prompt"] = SYSTEM_PROMPT_CHAT_REPLY

    session_actor = tool_init_user or recipient
    session_id, csrf_token = _create_session_and_csrf_for_user(session_actor)
    tool_init = _build_little_world_tool_init(
        session_id=session_id,
        csrf_token=csrf_token,
        api_host=_normalize_base_url_for_open_chat_tool(settings.BASE_URL),
        lw_chat_uuid=chat_uuid,
    )
    return _PreparedInteractionFlow(
        bot_config=bot_config,
        tool_init=tool_init,
        expected_tool_names={"little_world__chat_reply"},
    )


def _prepare_message_reply_suggestion_flow(
    *,
    configuration: OpenChatConfiguration,
    recipient: User,
    support_task_id: int | None,
    support_task_action_id: str,
    tool_init_user: User | None,
) -> _PreparedInteractionFlow:
    bot_config = _apply_bot_config_overwrite(
        _build_default_bot_config(
            tools=["little_world__generate_message_reply_suggestion"],
            system_prompt=SYSTEM_PROMPT_MESSAGE_REPLY_SUGGESTION,
        ),
        configuration.interaction_overwrite,
    )
    # Never allow per-user interaction_overwrite to disable the selected runtime tool mode.
    bot_config["tools"] = ["little_world__generate_message_reply_suggestion"]
    bot_config["system_prompt"] = SYSTEM_PROMPT_MESSAGE_REPLY_SUGGESTION

    session_actor = tool_init_user or recipient
    session_id, csrf_token = _create_session_and_csrf_for_user(session_actor)
    tool_init = _build_little_world_tool_init(
        session_id=session_id,
        csrf_token=csrf_token,
        api_host=_normalize_base_url_for_open_chat_tool(settings.BASE_URL),
        support_task_pk=support_task_id,
        support_task_action_id=support_task_action_id,
    )
    return _PreparedInteractionFlow(
        bot_config=bot_config,
        tool_init=tool_init,
        expected_tool_names={"little_world__generate_message_reply_suggestion"},
    )


def _collect_interaction_presence_stats(client: OpenChatPythonClient, interaction_uuid: str) -> dict:
    merged_payload = client.get_interactions(page=1, limit=40, all_pages=True)
    merged_rows = list(merged_payload.rows)

    return {
        "merged_count": len(merged_rows),
        "total_pages": merged_payload.total_pages,
        "present_in_merged": any(row.uuid == interaction_uuid for row in merged_rows),
    }


def _detect_expected_tool_call(
    client: OpenChatPythonClient,
    interaction_uuid: str,
    expected_tool_names: set[str],
) -> bool:
    if not expected_tool_names:
        return False

    interaction_messages_payload = client.list_interaction_messages(interaction_uuid, page=1, limit=200)
    interaction_messages = list(interaction_messages_payload.rows)
    for item in interaction_messages:
        tool_calls = item.tool_calls
        if any(_get_tool_call_name(tc) in expected_tool_names for tc in tool_calls):
            return True
    return False


def _run_open_chat_interaction_flow(
    *,
    configuration: OpenChatConfiguration,
    recipient: User,
    sender: User,
    chat_uuid: str,
    message_uuid: str,
    user_message_text: str,
    config_owner: str,
    tool_mode: str = OpenChatInteractionToolMode.CHAT_REPLY,
    publish_chat_interaction_message: bool = True,
    support_task_id: int | None = None,
    support_task_action_id: str | None = None,
    tool_init_user: User | None = None,
) -> dict:
    try:
        resolved_tool_mode = OpenChatInteractionToolMode(tool_mode)
    except ValueError:
        return {"status": "skipped", "reason": "invalid_tool_mode", "tool_mode": tool_mode}

    if resolved_tool_mode == OpenChatInteractionToolMode.CHAT_REPLY:
        prepared_flow = _prepare_chat_reply_flow(
            configuration=configuration,
            recipient=recipient,
            chat_uuid=chat_uuid,
            tool_init_user=tool_init_user,
        )
    elif resolved_tool_mode == OpenChatInteractionToolMode.MESSAGE_REPLY_SUGGESTION:
        if support_task_action_id is None:
            return {
                "status": "skipped",
                "reason": "support_task_action_missing_for_message_reply_suggestion",
                "support_task_id": support_task_id,
            }
        prepared_flow = _prepare_message_reply_suggestion_flow(
            configuration=configuration,
            recipient=recipient,
            support_task_id=support_task_id,
            support_task_action_id=support_task_action_id,
            tool_init_user=tool_init_user,
        )
    else:
        bot_config = _apply_bot_config_overwrite(
            _build_default_bot_config(
                tools=[],
                system_prompt=SYSTEM_PROMPT_NO_TOOLS,
            ),
            configuration.interaction_overwrite,
        )
        prepared_flow = _PreparedInteractionFlow(
            bot_config=bot_config,
            tool_init=None,
            expected_tool_names=set(),
        )

    try:
        client = OpenChatPythonClient(
            host=configuration.open_chat_host,
            username=configuration.open_chat_user,
            password=configuration.open_chat_api_key,
        )
        client.setup_bot_config(prepared_flow.bot_config)
        login_result = client.login()

        interaction_message = (user_message_text or "").strip() or FALLBACK_USER_MESSAGE
        if prepared_flow.tool_init is None:
            interaction = client.create_interaction(message=interaction_message)
        else:
            interaction = client.create_interaction(
                tool_init=prepared_flow.tool_init,
                message=interaction_message,
            )
        interaction_uuid = interaction.uuid
        login_user_name = login_result.name
        logger.info(
            "open_chat_interaction_flow login_user=%s config_owner=%s interaction_uuid=%s",
            login_user_name,
            config_owner,
            interaction_uuid,
        )

        presence_stats = _collect_interaction_presence_stats(client, interaction_uuid)
        if presence_stats["present_in_merged"] is False:
            return {
                "status": "error",
                "reason": "created_interaction_missing_from_get_interactions",
                "interaction_uuid": interaction_uuid,
                "total_pages": presence_stats["total_pages"],
                "merged_count": presence_stats["merged_count"],
            }

        shared_url = client.get_shared_interaction_url(interaction_uuid)
        tool_called = _detect_expected_tool_call(client, interaction_uuid, prepared_flow.expected_tool_names)

        interaction_message_uuid = None
        interaction_message_payload = None
        if interaction_uuid and publish_chat_interaction_message:
            from chat.consumers.messages import NewMessage
            from chat.models import ChatSerializer, MessageSerializer

            chat = Chat.objects.filter(uuid=chat_uuid).first()
            if chat is not None and chat.is_participant(sender) and chat.is_participant(recipient):
                interaction_message_payload = {
                    "type": "open_chat_interaction",
                    "title": "Tim: Very early experimental Open-Chat integration, use with caution",
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
            "login_user_name": login_user_name,
            "interaction_message_input": user_message_text,
            "interaction_uuid": interaction_uuid,
            "shared_url": shared_url,
            "tool_called": tool_called,
            "interaction_total_pages": presence_stats["total_pages"],
            "interaction_merged_count": presence_stats["merged_count"],
            "interaction_present_in_merged": presence_stats["present_in_merged"],
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

    created_by_user = resolve_open_chat_automation_task_creator_user()
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

        step_result = create_or_reuse_support_reply_task_for_message(
            latest_message=latest_message,
            source_user=source_user,
            target_user=target_user,
            created_by_user=created_by_user,
            assigned_to_user=assigned_to_user,
            configuration_user_uuid=str(configuration.user.uuid),
            enqueue_interaction=True,
        )
        if step_result["status"] in {"created", "created_and_enqueued"}:
            created_tasks += 1
        if step_result["status"] == "created_and_enqueued":
            enqueued_interactions += 1
        processed_messages.append(step_result)

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
    tool_mode: str = OpenChatInteractionToolMode.CHAT_REPLY.value,
    publish_chat_interaction_message: bool = True,
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

    try:
        resolved_tool_mode = OpenChatInteractionToolMode(tool_mode)
    except ValueError:
        return {"status": "skipped", "reason": "invalid_tool_mode", "tool_mode": tool_mode}

    support_task_action_id: str | None = None
    tool_init_user: User | None = None
    if support_task_id is not None and resolved_tool_mode == OpenChatInteractionToolMode.MESSAGE_REPLY_SUGGESTION:
        support_action = (
            SupportTaskAction.objects.select_related("task", "task__created_by").filter(task_id=support_task_id).first()
        )
        if support_action is None:
            return {
                "status": "skipped",
                "reason": "support_task_action_missing",
                "support_task_id": support_task_id,
            }
        if support_action.status != SupportTaskAction.Status.OPEN:
            return {
                "status": "skipped",
                "reason": "support_task_action_not_open",
                "support_task_id": support_task_id,
                "support_task_action_id": support_action.pk,
                "support_task_action_status": support_action.status,
            }
        support_task_action_id = str(support_action.pk)
        tool_init_user = support_action.task.created_by

    result = _run_open_chat_interaction_flow(
        configuration=configuration,
        recipient=recipient,
        sender=sender,
        chat_uuid=chat_uuid,
        message_uuid=message_uuid,
        user_message_text=user_message_text,
        config_owner="explicit_configuration_user",
        tool_mode=resolved_tool_mode.value,
        publish_chat_interaction_message=publish_chat_interaction_message,
        support_task_id=support_task_id,
        support_task_action_id=support_task_action_id,
        tool_init_user=tool_init_user,
    )
    if support_task_id and result["status"] == "ok" and result["interaction_uuid"]:
        support_action = SupportTaskAction.objects.filter(task_id=support_task_id).first()
        if support_action is not None:
            static_parameters = dict(support_action.static_parameters or {})
            static_parameters["interaction_id"] = str(result["interaction_uuid"])
            static_parameters["shared_interaction_url"] = result["shared_url"]
            support_action.static_parameters = static_parameters
            support_action.save(update_fields=["static_parameters"])
    return result
