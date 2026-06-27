from client import OpenChatClient, RESTToolBuilder

from open_chat.rest_tool_schema import (
    SESSION_AUTH_HEADER_PARAMS,
    openapi_doc_with_server,
    with_hostname_policy,
    with_session_auth,
)

CHAT_REPLY_REST_TOOL_NAME = "little_world_chat_reply"
MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME = "little_world_message_reply_suggestion"
API_HOST_INIT_FIELD = "api_host"

CHAT_SEND_PATH = "/api/messages/{chat_uuid}/send/"
SUPPORT_TASK_ACTION_PATH = "/api/support_task/{task_pk}/action/"

_REST_TOOL_NAMES = (CHAT_REPLY_REST_TOOL_NAME, MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME)


def build_chat_reply_rest_tool_definition(api_host: str | None = None) -> RESTToolBuilder:
    operation_id, openapi_doc, hostname = openapi_doc_with_server(
        path=CHAT_SEND_PATH,
        method="post",
        info_title="Little World Chat Reply Tool API",
        extra_parameters=SESSION_AUTH_HEADER_PARAMS,
        component_schema_names=("SendMessage",),
        api_host=api_host,
    )
    builder = (
        RESTToolBuilder(
            CHAT_REPLY_REST_TOOL_NAME,
            "Send a support response to a Little World chat conversation.",
        )
        .openapi_inline(openapi_doc)
        .operation(operation_id)
        .base_url_from_init(API_HOST_INIT_FIELD)
        .bind_init("chat_uuid")
        .to_path("chat_uuid")
        .bind_call("message")
        .to_body("text")
    )
    return with_hostname_policy(with_session_auth(builder), hostname).enable()


def build_message_reply_suggestion_rest_tool_definition(api_host: str | None = None) -> RESTToolBuilder:
    operation_id, openapi_doc, hostname = openapi_doc_with_server(
        path=SUPPORT_TASK_ACTION_PATH,
        method="patch",
        info_title="Little World Message Reply Suggestion Tool API",
        extra_parameters=SESSION_AUTH_HEADER_PARAMS,
        api_host=api_host,
    )
    builder = (
        RESTToolBuilder(
            MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
            "Persist a generated support reply draft on an open support task action.",
        )
        .openapi_inline(openapi_doc)
        .operation(operation_id)
        .base_url_from_init(API_HOST_INIT_FIELD)
        .bind_init("task_pk")
        .to_path("task_pk")
        .bind_call("parameters")
        .to_body("parameters")
    )
    return with_hostname_policy(with_session_auth(builder), hostname).enable()


def build_all_rest_tool_definitions(api_host: str | None = None) -> list[RESTToolBuilder]:
    return [
        build_chat_reply_rest_tool_definition(api_host=api_host),
        build_message_reply_suggestion_rest_tool_definition(api_host=api_host),
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
