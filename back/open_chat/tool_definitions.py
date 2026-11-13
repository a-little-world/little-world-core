from client import OpenChatClient, RESTToolBuilder

from open_chat.rest_tool_schema import (
    API_HOST_INIT_FIELD,
    SESSION_AUTH_HEADER_PARAMS,
    allow_local_tool_hosts,
    resolve_api_host,
    spectacular_schema,
)
from open_chat.tool_definitions_management import (
    MANAGEMENT_REST_TOOL_NAMES,
    build_all_management_rest_tool_definitions,
)

CHAT_REPLY_REST_TOOL_NAME = "little_world_chat_reply"
MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME = "little_world_message_reply_suggestion"
RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME = "little_world_retrieve_past_messages"
RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME = "little_world_retrieve_management_permissions"

CHAT_SEND_PATH = "/api/messages/{chat_uuid}/send/"
CHAT_MESSAGES_LIST_PATH = "/api/messages/{chat_uuid}/"
SUPPORT_TASK_ACTION_PATH = "/api/support_task/{task_pk}/action/"
MATCHING_PANEL_ME_PATH = "/api/matching/me/"

_REST_TOOL_NAMES = (
    CHAT_REPLY_REST_TOOL_NAME,
    MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
    RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
    RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
    *MANAGEMENT_REST_TOOL_NAMES,
)


def build_chat_reply_rest_tool_definition(api_host: str | None = None) -> RESTToolBuilder:
    resolved_api_host, hostname = resolve_api_host(api_host)
    builder = (
        RESTToolBuilder(
            CHAT_REPLY_REST_TOOL_NAME,
            (
                "Send the final support reply to the Little World user in chat. "
                "You MUST call this tool exactly once as your last step. "
                "Pass the complete user-visible reply in the `message` argument. "
                "Wrap links in Little World chat anchor markup with href and target=_blank "
                "(never bare URLs). "
                "If you do not call this tool, the user will not receive any response."
            ),
        )
        .openapi_endpoint(
            spectacular_schema(),
            path=CHAT_SEND_PATH,
            method="post",
            info_title="Little World Chat Reply Tool API",
            extra_parameters=SESSION_AUTH_HEADER_PARAMS,
            servers=[{"url": resolved_api_host}],
        )
        .base_url_from_init(API_HOST_INIT_FIELD)
        .bind_init("chat_uuid")
        .to_path("chat_uuid")
        .bind_session_auth()
        .bind_call("message")
        .to_body("text")
    )
    return allow_local_tool_hosts(builder, hostname).enable()


def build_message_reply_suggestion_rest_tool_definition(api_host: str | None = None) -> RESTToolBuilder:
    resolved_api_host, hostname = resolve_api_host(api_host)
    builder = (
        RESTToolBuilder(
            MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
            (
                "Persist the final suggested outcome on the open support task action. "
                "You MUST call this tool exactly once as your last step with the complete "
                '`parameters`, e.g. {"suggested_action": "reply", "message": "<full suggested reply>"}. '
                "`parameters.suggested_action` is one of: "
                '"reply" (default, user-visible reply in `message`), '
                '"mark_read" (mark the user message read and close the ticket), '
                '"slack_feedback" (post `slack_message` to the Slack thread `slack_thread`), '
                '"keep_open" (keep the ticket open, optional `scheduled_at` and `note`). '
                "If you do not call this tool, no suggestion is saved for the support task."
            ),
        )
        .openapi_endpoint(
            spectacular_schema(),
            path=SUPPORT_TASK_ACTION_PATH,
            method="patch",
            info_title="Little World Message Reply Suggestion Tool API",
            extra_parameters=SESSION_AUTH_HEADER_PARAMS,
            servers=[{"url": resolved_api_host}],
        )
        .base_url_from_init(API_HOST_INIT_FIELD)
        .bind_init("task_pk")
        .to_path("task_pk")
        .bind_session_auth()
        .bind_call("parameters")
        .to_body("parameters")
    )
    return allow_local_tool_hosts(builder, hostname).enable()


def build_retrieve_past_messages_rest_tool_definition(api_host: str | None = None) -> RESTToolBuilder:
    resolved_api_host, hostname = resolve_api_host(api_host)
    builder = (
        RESTToolBuilder(
            RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
            "List past messages in a Little World chat conversation.",
        )
        .openapi_endpoint(
            spectacular_schema(),
            path=CHAT_MESSAGES_LIST_PATH,
            method="get",
            info_title="Little World Retrieve Past Messages Tool API",
            extra_parameters=SESSION_AUTH_HEADER_PARAMS,
            servers=[{"url": resolved_api_host}],
        )
        .base_url_from_init(API_HOST_INIT_FIELD)
        .bind_init("chat_uuid")
        .to_path("chat_uuid")
        .bind_session_auth()
        .bind_call("page")
        .to_query("page")
        .bind_call("page_size")
        .to_query("page_size")
    )
    builder = builder.censor_response_paths("results.*.text")
    return allow_local_tool_hosts(builder, hostname).enable()


def build_retrieve_management_permissions_rest_tool_definition(api_host: str | None = None) -> RESTToolBuilder:
    resolved_api_host, hostname = resolve_api_host(api_host)
    builder = (
        RESTToolBuilder(
            RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
            "Retrieve the current user's Little World management panel permissions.",
        )
        .openapi_endpoint(
            spectacular_schema(),
            path=MATCHING_PANEL_ME_PATH,
            method="get",
            info_title="Little World Retrieve Management Permissions Tool API",
            extra_parameters=SESSION_AUTH_HEADER_PARAMS,
            servers=[{"url": resolved_api_host}],
        )
        .base_url_from_init(API_HOST_INIT_FIELD)
        .bind_session_auth()
    )
    builder = builder.censor_response_paths("email", "first_name", "last_name")
    return allow_local_tool_hosts(builder, hostname).enable()


def build_all_rest_tool_definitions(api_host: str | None = None) -> list[RESTToolBuilder]:
    return [
        build_chat_reply_rest_tool_definition(api_host=api_host),
        build_message_reply_suggestion_rest_tool_definition(api_host=api_host),
        build_retrieve_past_messages_rest_tool_definition(api_host=api_host),
        build_retrieve_management_permissions_rest_tool_definition(api_host=api_host),
        *build_all_management_rest_tool_definitions(api_host=api_host),
    ]


def ensure_rest_tool_definitions(client: OpenChatClient) -> dict[str, list[str]]:
    """Create missing REST tools and refresh interaction-critical tool definitions on Open Chat."""
    tools = build_all_rest_tool_definitions()
    existing = {str(row.get("name")) for row in client.list_dynamic_rest_tools() if row.get("name")}

    created: list[str] = []
    updated: list[str] = []
    refresh_names = {CHAT_REPLY_REST_TOOL_NAME, MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME}
    for name, tool in zip(_REST_TOOL_NAMES, tools, strict=True):
        if name not in existing:
            client.save_dynamic_rest_tool(tool)
            created.append(name)
            continue
        if name in refresh_names:
            client.save_dynamic_rest_tool(tool)
            updated.append(name)
    return {"created": created, "updated": updated}


def sync_rest_tool_definitions(client: OpenChatClient, *, reload: bool = False) -> dict[str, list[str]]:
    tools = build_all_rest_tool_definitions()
    existing = {str(row.get("name")) for row in client.list_dynamic_rest_tools() if row.get("name")}

    result = {"created": [], "updated": [], "deleted": []}

    if reload:
        for name in sorted(set(_REST_TOOL_NAMES) & existing):
            client.delete_dynamic_rest_tool(name)
            result["deleted"].append(name)
        for name, tool in zip(_REST_TOOL_NAMES, tools, strict=True):
            client.save_dynamic_rest_tool(tool)
            result["created"].append(name)
        return result

    for name, tool in zip(_REST_TOOL_NAMES, tools, strict=True):
        client.save_dynamic_rest_tool(tool)
        if name in existing:
            result["updated"].append(name)
        else:
            result["created"].append(name)
    return result
