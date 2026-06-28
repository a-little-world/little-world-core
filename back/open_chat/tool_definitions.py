from client import OpenChatClient, RESTToolBuilder

from open_chat.rest_tool_schema import SESSION_AUTH_HEADER_PARAMS, resolve_api_host, spectacular_schema

CHAT_REPLY_REST_TOOL_NAME = "little_world_chat_reply"
MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME = "little_world_message_reply_suggestion"
RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME = "little_world_retrieve_past_messages"
RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME = "little_world_retrieve_management_permissions"
API_HOST_INIT_FIELD = "api_host"

CHAT_SEND_PATH = "/api/messages/{chat_uuid}/send/"
CHAT_MESSAGES_LIST_PATH = "/api/messages/{chat_uuid}/"
SUPPORT_TASK_ACTION_PATH = "/api/support_task/{task_pk}/action/"
MATCHING_PANEL_ME_PATH = "/api/matching/me/"

_REST_TOOL_NAMES = (
    CHAT_REPLY_REST_TOOL_NAME,
    MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
    RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
    RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
)


def build_chat_reply_rest_tool_definition(api_host: str | None = None) -> RESTToolBuilder:
    resolved_api_host, hostname = resolve_api_host(api_host)
    return (
        RESTToolBuilder(
            CHAT_REPLY_REST_TOOL_NAME,
            "Send a support response to a Little World chat conversation.",
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
        .allow_hostname_policy(hostname)
        .enable()
    )


def build_message_reply_suggestion_rest_tool_definition(api_host: str | None = None) -> RESTToolBuilder:
    resolved_api_host, hostname = resolve_api_host(api_host)
    return (
        RESTToolBuilder(
            MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
            "Persist a generated support reply draft on an open support task action.",
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
        .allow_hostname_policy(hostname)
        .enable()
    )


def build_retrieve_past_messages_rest_tool_definition(api_host: str | None = None) -> RESTToolBuilder:
    resolved_api_host, hostname = resolve_api_host(api_host)
    return (
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
        .allow_hostname_policy(hostname)
        .enable()
    )


def build_retrieve_management_permissions_rest_tool_definition(api_host: str | None = None) -> RESTToolBuilder:
    resolved_api_host, hostname = resolve_api_host(api_host)
    return (
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
        .allow_hostname_policy(hostname)
        .enable()
    )


def build_all_rest_tool_definitions(api_host: str | None = None) -> list[RESTToolBuilder]:
    return [
        build_chat_reply_rest_tool_definition(api_host=api_host),
        build_message_reply_suggestion_rest_tool_definition(api_host=api_host),
        build_retrieve_past_messages_rest_tool_definition(api_host=api_host),
        build_retrieve_management_permissions_rest_tool_definition(api_host=api_host),
    ]


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
