import json
import logging

from celery import shared_task
from chat.models import Chat
from chat.models import Message as ChatMessage
from client import OpenChatClient, PasswordAuth
from management.models.user import User
from management.permissions import ManagementPermission

from open_chat.helpers import (
    FALLBACK_USER_MESSAGE,
    build_chat_text_markup_hint,
    build_session_tool_init_payload,
    build_tool_session_context,
    little_world_panel_base_url,
    value_or,
)
from open_chat.interaction_config import (
    DEFAULT_OPEN_CHAT_BASIC_TEMPERATURE,
    DEFAULT_OPEN_CHAT_MESSAGE_CONTEXT,
    build_interaction_overrides,
)
from open_chat.models import OpenChatConfiguration
from open_chat.tool_definitions import (
    CHAT_REPLY_REST_TOOL_NAME,
    RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
    RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
    ensure_rest_tool_definitions,
)
from open_chat.tool_definitions_management import (
    GET_DYNAMIC_USER_LIST_REST_TOOL_NAME,
    GET_MATCH_DETAIL_REST_TOOL_NAME,
    GET_MATCH_NOTES_REST_TOOL_NAME,
    GET_SCORE_DETAIL_REST_TOOL_NAME,
    GET_SUPPORT_TASK_DETAIL_REST_TOOL_NAME,
    GET_SUPPORT_TASK_STATS_REST_TOOL_NAME,
    GET_USER_DETAIL_REST_TOOL_NAME,
    GET_USER_EMAILS_REST_TOOL_NAME,
    GET_USER_MATCH_WAITING_TIME_REST_TOOL_NAME,
    GET_USER_MESSAGES_REST_TOOL_NAME,
    GET_USER_NOTES_REST_TOOL_NAME,
    GET_USER_PREMATCHING_APPOINTMENT_REST_TOOL_NAME,
    GET_USER_SMS_REST_TOOL_NAME,
    GET_USER_TASKS_REST_TOOL_NAME,
    GET_VIDEO_CALL_DETAIL_REST_TOOL_NAME,
    LIST_DYNAMIC_USER_LISTS_REST_TOOL_NAME,
    LIST_MATCH_FILTERS_REST_TOOL_NAME,
    LIST_SCORE_FILTERS_REST_TOOL_NAME,
    LIST_SUPPORT_STAFF_REST_TOOL_NAME,
    LIST_USER_FILTERS_REST_TOOL_NAME,
    LIST_VIDEO_CALL_FILTERS_REST_TOOL_NAME,
    QUERY_MATCHES_REST_TOOL_NAME,
    QUERY_PREMATCHING_APPOINTMENTS_REST_TOOL_NAME,
    QUERY_SCORES_REST_TOOL_NAME,
    QUERY_SUPPORT_TASKS_REST_TOOL_NAME,
    QUERY_USERS_REST_TOOL_NAME,
    QUERY_VIDEO_CALLS_REST_TOOL_NAME,
    SUPPORT_TASK_USER_SEARCH_REST_TOOL_NAME,
    build_management_tool_init,
)

logger = logging.getLogger(__name__)

# Pre-provisioned Open Chat bot that owns the live chat-reply interaction config.
CHAT_REPLY_BOT = "little_world_support_chat"
BASIC_CHAT_INTERACTION_CONTEXT = DEFAULT_OPEN_CHAT_MESSAGE_CONTEXT

_BASIC_CHAT_MANAGEMENT_TOOL_NAMES = (
    LIST_USER_FILTERS_REST_TOOL_NAME,
    LIST_MATCH_FILTERS_REST_TOOL_NAME,
    LIST_VIDEO_CALL_FILTERS_REST_TOOL_NAME,
    LIST_SCORE_FILTERS_REST_TOOL_NAME,
    LIST_DYNAMIC_USER_LISTS_REST_TOOL_NAME,
    QUERY_USERS_REST_TOOL_NAME,
    QUERY_MATCHES_REST_TOOL_NAME,
    QUERY_VIDEO_CALLS_REST_TOOL_NAME,
    QUERY_SCORES_REST_TOOL_NAME,
    QUERY_SUPPORT_TASKS_REST_TOOL_NAME,
    QUERY_PREMATCHING_APPOINTMENTS_REST_TOOL_NAME,
    GET_USER_DETAIL_REST_TOOL_NAME,
    GET_MATCH_DETAIL_REST_TOOL_NAME,
    GET_VIDEO_CALL_DETAIL_REST_TOOL_NAME,
    GET_SCORE_DETAIL_REST_TOOL_NAME,
    GET_SUPPORT_TASK_DETAIL_REST_TOOL_NAME,
    GET_DYNAMIC_USER_LIST_REST_TOOL_NAME,
    GET_USER_MESSAGES_REST_TOOL_NAME,
    GET_USER_TASKS_REST_TOOL_NAME,
    GET_USER_NOTES_REST_TOOL_NAME,
    GET_USER_MATCH_WAITING_TIME_REST_TOOL_NAME,
    GET_USER_PREMATCHING_APPOINTMENT_REST_TOOL_NAME,
    GET_USER_SMS_REST_TOOL_NAME,
    GET_USER_EMAILS_REST_TOOL_NAME,
    GET_MATCH_NOTES_REST_TOOL_NAME,
    GET_SUPPORT_TASK_STATS_REST_TOOL_NAME,
    SUPPORT_TASK_USER_SEARCH_REST_TOOL_NAME,
    LIST_SUPPORT_STAFF_REST_TOOL_NAME,
)


def build_basic_chat_interaction_system_prompt() -> str:
    base_url = little_world_panel_base_url()
    return f"""
You are a Little World support assistant helping staff respond to user chat messages and answer platform questions.

This Open Chat thread is an internal workspace only. Text you write here is NOT delivered to the Little World user.

Workflow:
1. Use available tools to gather conversation history, permissions, and platform data when needed.
2. Compose a helpful, complete reply for the Little World user (use chat markup below for links).
3. You MUST finish by calling `{CHAT_REPLY_REST_TOOL_NAME}` exactly once. Pass the full reply in the tool's `message` parameter.

Rules:
- Never answer the user with plain assistant text in this thread — not even for permission lookups or platform summaries.
- Every user-visible answer MUST be sent through `{CHAT_REPLY_REST_TOOL_NAME}` exactly once as your last step.
- Put the user-visible reply (including any link markup) in the `message` argument of `{CHAT_REPLY_REST_TOOL_NAME}`, not in assistant text here.
- If you already used retrieval or lookup tools, you still MUST call `{CHAT_REPLY_REST_TOOL_NAME}` afterward with the complete reply in `message`.
- Do not skip `{CHAT_REPLY_REST_TOOL_NAME}` under any circumstances. The interaction is incomplete until this tool succeeds.
- Non-staff matching users only see users in their managed scope; mention this if results seem limited.
- Keep tool payloads small: use page_size=5 for query_* tools by default, page_size=1 when you only need a count (read items_total), and get_*_detail for a single record instead of broad list queries when possible.
- Before building non-trivial query_* filters, call `{LIST_USER_FILTERS_REST_TOOL_NAME}` (or the matching list_*_filters tool) to read valid filter names and choice values. Pass query params as scalars, never JSON arrays; omit order_by unless you need a non-default sort.
- Use `{GET_USER_DETAIL_REST_TOOL_NAME}` with path param `id` (numeric id, uuid, or email) to load one user's full profile (including interests).
- Use `{GET_MATCH_DETAIL_REST_TOOL_NAME}` with path param `id` (match id or uuid) to load one match's full detail.
- List filters do not cover interests/hobbies. After narrowing with `{QUERY_USERS_REST_TOOL_NAME}`, read `profile.interests` from result rows (paginate if needed) or call `{GET_USER_DETAIL_REST_TOOL_NAME}` per user.
- When including admin panel links, wrap each in `<a {{"href": "...", "target": "_blank"}}>label</a>` using the base URL below. Never paste bare URLs.
- List links with page_size must use page_size=20 or higher — never below 20.
- For one specific user, link `/matching/user/{{numeric_id}}` (optionally `?tab=chat|emails|calls|matches|stats|notes|actions`). Never link `/matching/users/?search=…` when you know the user's id.
- Use `/matching/users/?…` only for filtered list views (cohorts). Use `/matching/match/{{id}}` for a specific match.

{build_chat_text_markup_hint(base_url)}

Reminder: your last action must be `{CHAT_REPLY_REST_TOOL_NAME}` with the formatted reply in `message`.
""".strip()


BASIC_CHAT_INTERACTION_SYSTEM_PROMPT = build_basic_chat_interaction_system_prompt()


def _basic_chat_interaction_overrides() -> dict[str, object]:
    return build_interaction_overrides(
        system_prompt=build_basic_chat_interaction_system_prompt(),
        context=BASIC_CHAT_INTERACTION_CONTEXT,
        temperature=DEFAULT_OPEN_CHAT_BASIC_TEMPERATURE,
        tools=[
            RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
            RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
            *_BASIC_CHAT_MANAGEMENT_TOOL_NAMES,
            CHAT_REPLY_REST_TOOL_NAME,
        ],
    )


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
        "title": "Tim: LLMs may hallucinate, always verify outputs and conclusions",
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
    3) enqueue a chat-reply interaction and publish the shared link back into the chat
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

    session_actor = sender
    actor_session_id, actor_csrf_token, api_host = build_tool_session_context(session_actor)
    bot_session_id, bot_csrf_token, _ = build_tool_session_context(recipient)
    try:
        client = OpenChatClient(
            base_url=configuration.open_chat_host,
            auth=PasswordAuth(email=configuration.open_chat_user, password=configuration.open_chat_api_key),
        )
        login_user = client.login()
        ensure_rest_tool_definitions(client)

        actor_session_init = build_session_tool_init_payload(
            api_host=api_host,
            session_id=actor_session_id,
            csrf_token=actor_csrf_token,
        )
        bot_session_init = build_session_tool_init_payload(
            api_host=api_host,
            session_id=bot_session_id,
            csrf_token=bot_csrf_token,
        )
        message = (user_message_text or "").strip() or FALLBACK_USER_MESSAGE
        interaction = client.interact(
            bot=CHAT_REPLY_BOT,
            message=message,
            share=True,
            overrides=_basic_chat_interaction_overrides(),
            tool_init={
                CHAT_REPLY_REST_TOOL_NAME: {
                    **bot_session_init,
                    "chat_uuid": chat_uuid,
                },
                RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME: {
                    **actor_session_init,
                    "chat_uuid": chat_uuid,
                },
                RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME: actor_session_init,
                **build_management_tool_init(actor_session_init),
            },
        )
        interaction_uuid = interaction.uuid
        shared_url = interaction.shared_url()
        login_user_name = value_or(login_user.name, "")
        logger.info(
            "open_chat_basic_chat_interaction enqueued login_user=%s config_owner=%s session_actor=%s session_bot=%s interaction_uuid=%s shared_url=%s",
            login_user_name,
            config_owner,
            session_actor.email,
            recipient.email,
            interaction_uuid,
            shared_url,
        )

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
            "session_actor_user_id": session_actor.pk,
            "session_actor_email": session_actor.email,
            "session_bot_user_id": recipient.pk,
            "session_bot_email": recipient.email,
            "login_user_name": login_user_name,
            "interaction_uuid": interaction_uuid,
            "shared_url": shared_url,
            "interaction_message_uuid": interaction_message_uuid,
            "interaction_message_payload": interaction_message_payload,
        }
    except Exception as exc:
        return {"status": "error", "reason": "open_chat_interaction_failed", "detail": str(exc)}
