import logging

from celery import current_app, shared_task
from chat.models import Message as ChatMessage
from client.client import OpenChatPythonClient
from django.db.models import Q

from management import controller
from management.helpers.open_chat import (
    FALLBACK_USER_MESSAGE,
    _apply_bot_config_overwrite,
    build_default_bot_config,
    build_tool_session_context,
    detect_expected_tool_call,
    resolve_open_chat_automation_task_creator_user,
    value_or,
)
from management.models.open_chat_configuration import OpenChatConfiguration
from management.models.support_task import SupportTask, SupportTaskAction
from management.models.user import User
from management.permissions import ManagementPermission

logger = logging.getLogger(__name__)

RUN_INTERACTION_TASK_NAME = "management.tasks.open_chat_run_message_reply_suggestion_interaction"

SUGGESTION_TOOL = "little_world__generate_message_reply_suggestion"

SYSTEM_PROMPT_MESSAGE_REPLY_SUGGESTION = """
Du bearbeitest eine Little-World-Support-Konversation.
Erstelle eine kurze und hilfreiche finale Antwort auf die letzte Nutzernachricht.
Rufe genau einmal das Tool `little_world__generate_message_reply_suggestion` auf, um den Entwurf zu speichern.
Stelle niemals Rueckfragen und bitte niemals um mehr Informationen.
Wenn die Eingabe unklar oder sehr kurz ist, erstelle trotzdem einen bestmoeglichen, freundlichen Antwortentwurf.
Frage nicht nach einer Bestaetigung und rufe keine anderen Tools auf.
Uebergib als Argument nur den Entwurfstext in `message`.
""".strip()


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
    """Run a single message-reply-suggestion interaction and store the draft on the support task."""
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

    bot_config = _apply_bot_config_overwrite(
        build_default_bot_config(tools=[SUGGESTION_TOOL], system_prompt=SYSTEM_PROMPT_MESSAGE_REPLY_SUGGESTION),
        configuration.interaction_overwrite,
    )
    # Never allow per-user interaction_overwrite to disable the selected runtime tool mode.
    bot_config["tools"] = [SUGGESTION_TOOL]
    bot_config["system_prompt"] = SYSTEM_PROMPT_MESSAGE_REPLY_SUGGESTION

    session_id, csrf_token, api_host = build_tool_session_context(support_action.task.created_by or recipient)
    tool_init = {
        SUGGESTION_TOOL: {
            "session_id": session_id,
            "csrf_token": csrf_token,
            "api_host": api_host,
            "task_pk": str(support_action.task.pk),
            "action_id": str(support_action.pk),
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
            "open_chat_run_message_reply_suggestion login_user=%s support_task_id=%s interaction_uuid=%s",
            login_user_name,
            support_action.task.pk,
            interaction_uuid,
        )

        shared_url = client.get_shared_interaction_url(interaction_uuid)
        tool_called = detect_expected_tool_call(client, interaction_uuid, {SUGGESTION_TOOL})
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
        "tool_called": tool_called,
        "support_task_id": support_action.task.pk,
        "support_task_action_id": support_action.pk,
    }
