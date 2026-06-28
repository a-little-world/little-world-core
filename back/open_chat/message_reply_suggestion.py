import logging

from celery import current_app, shared_task
from chat.models import Message as ChatMessage
from client import OpenChatClient, PasswordAuth
from django.db.models import Q
from management import controller
from management.models.support_task import SupportTask, SupportTaskAction
from management.models.user import User
from management.permissions import ManagementPermission

from open_chat.helpers import (
    FALLBACK_USER_MESSAGE,
    build_session_tool_init_payload,
    build_tool_session_context,
    resolve_open_chat_automation_task_creator_user,
    value_or,
)
from open_chat.models import OpenChatConfiguration
from open_chat.tool_definitions import (
    MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
    RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
    ensure_rest_tool_definitions,
)

logger = logging.getLogger(__name__)

RUN_INTERACTION_TASK_NAME = "management.tasks.open_chat_run_message_reply_suggestion_interaction"

# Pre-provisioned Open Chat bot that owns the message-reply-suggestion interaction config.
SUGGESTION_BOT = "little_world_reply_suggestion"
MESSAGE_REPLY_SUGGESTION_CONTEXT = 10000

MESSAGE_REPLY_SUGGESTION_SYSTEM_PROMPT = f"""
You are a Little World support assistant helping staff draft replies to user messages.

This Open Chat thread is an internal workspace only. Text you write here is NOT saved as a support reply suggestion.

Your tools:
- `{RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME}` — load earlier messages in the current conversation for context.
- `{MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME}` — the ONLY way to persist a reply draft on the open support task.

Workflow:
1. Use `{RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME}` when you need more conversation context.
2. Draft a helpful support reply based on the latest user message and any context you retrieved.
3. You MUST finish by calling `{MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME}` exactly once with the complete draft
   in `parameters`, e.g. `{{"message": "<your full suggested reply>"}}`.

Rules:
- Never treat plain assistant text in this thread as the saved suggestion.
- Do not skip `{MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME}` — if you skip it, nothing is stored on the support task.
- If you already used `{RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME}`, still call `{MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME}` afterward.
""".strip()


def _message_reply_suggestion_overrides() -> dict[str, object]:
    return {
        "system_prompt": MESSAGE_REPLY_SUGGESTION_SYSTEM_PROMPT,
        "context": MESSAGE_REPLY_SUGGESTION_CONTEXT,
        "tools": [
            RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
            MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
        ],
    }


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
            static_parameters__sender_user_id=source_user.pk,
        )
        .first()
    )
    if existing_action is not None:
        if existing_action.task.assigned_to is None:
            SupportTask.objects.filter(pk=existing_action.task.pk).update(assigned_to_id=assigned_to_user.pk)
        has_suggestion = bool((existing_action.parameters or {}).get("message", "").strip())
        result = {
            "message_uuid": str(latest_message.uuid),
            "chat_uuid": str(latest_message.chat.uuid),
            "support_task_id": existing_action.task.pk,
            "status": "skipped_duplicate",
        }
        if not has_suggestion and enqueue_interaction and configuration_user_uuid:
            interaction_task = current_app.send_task(  # pyright: ignore[reportCallIssue]
                RUN_INTERACTION_TASK_NAME,
                kwargs={
                    "configuration_user_uuid": configuration_user_uuid,
                    "chat_uuid": str(latest_message.chat.uuid),
                    "message_uuid": str(latest_message.uuid),
                    "sender_uuid": str(source_user.uuid),
                    "recipient_uuid": str(target_user.uuid),
                    "user_message_text": latest_message.text or "",
                    "support_task_id": existing_action.task.pk,
                },
            )
            result["interaction_task_id"] = interaction_task.id
            result["status"] = "reused_and_enqueued"
        return result

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
        RUN_INTERACTION_TASK_NAME,
        kwargs={
            "configuration_user_uuid": configuration_user_uuid,
            "chat_uuid": str(latest_message.chat.uuid),
            "message_uuid": str(latest_message.uuid),
            "sender_uuid": str(source_user.uuid),
            "recipient_uuid": str(target_user.uuid),
            "user_message_text": latest_message.text or "",
            "support_task_id": support_task.pk,
        },
    )
    result["interaction_task_id"] = interaction_task.id
    result["status"] = "created_and_enqueued"
    return result


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

    from management.api.user_advanced_filter import get_user_with_message_to_admin

    # Only suggest replies for users whose latest message to the management user
    # is still unread (i.e. not yet handled). Read messages are skipped.
    pending_users = list(get_user_with_message_to_admin(User.objects.filter(is_active=True)))
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
        if step_result["status"] in {"created_and_enqueued", "reused_and_enqueued"}:
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


@shared_task(name=RUN_INTERACTION_TASK_NAME)
def open_chat_run_message_reply_suggestion_interaction(
    configuration_user_uuid: str,
    chat_uuid: str,
    message_uuid: str,
    sender_uuid: str,
    recipient_uuid: str,
    user_message_text: str = "",
    support_task_id: int | None = None,
):
    """Enqueue a message-reply-suggestion interaction; Open Chat updates the task asynchronously."""
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

    support_action = (
        SupportTaskAction.objects.select_related("task", "task__created_by").filter(task_id=support_task_id).first()
        if support_task_id is not None
        else None
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

    session_id, csrf_token, api_host = build_tool_session_context(support_action.task.created_by or recipient)
    try:
        client = OpenChatClient(
            base_url=configuration.open_chat_host,
            auth=PasswordAuth(email=configuration.open_chat_user, password=configuration.open_chat_api_key),
        )
        login_user = client.login()
        ensure_rest_tool_definitions(client)

        session_init = build_session_tool_init_payload(
            api_host=api_host,
            session_id=session_id,
            csrf_token=csrf_token,
        )
        message = (user_message_text or "").strip() or FALLBACK_USER_MESSAGE
        interaction = client.interact(
            bot=SUGGESTION_BOT,
            message=message,
            share=True,
            overrides=_message_reply_suggestion_overrides(),
            tool_init={
                MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME: {
                    **session_init,
                    "task_pk": support_action.task.pk,
                },
                RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME: {
                    **session_init,
                    "chat_uuid": chat_uuid,
                },
            },
        )
        interaction_uuid = interaction.uuid
        shared_url = interaction.shared_url()
        login_user_name = value_or(login_user.name, "")
        logger.info(
            "open_chat_run_message_reply_suggestion enqueued login_user=%s support_task_id=%s interaction_uuid=%s shared_url=%s",
            login_user_name,
            support_action.task.pk,
            interaction_uuid,
            shared_url,
        )
    except Exception as exc:
        return {"status": "error", "reason": "open_chat_interaction_failed", "detail": str(exc)}

    static_parameters = dict(support_action.static_parameters or {})
    static_parameters["interaction_id"] = interaction_uuid
    static_parameters["shared_interaction_url"] = shared_url
    support_action.static_parameters = static_parameters
    support_action.save(update_fields=["static_parameters"])

    return {
        "status": "ok",
        "chat_uuid": chat_uuid,
        "message_uuid": message_uuid,
        "sender_uuid": str(sender.uuid),
        "recipient_uuid": str(recipient.uuid),
        "configuration_user_id": configuration.user.pk,
        "login_user_name": login_user_name,
        "interaction_uuid": interaction_uuid,
        "shared_url": shared_url,
        "support_task_id": support_action.task.pk,
        "support_task_action_id": support_action.pk,
    }
