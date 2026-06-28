import json
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from open_chat.tool_definitions import (
    CHAT_MESSAGES_LIST_PATH,
    CHAT_REPLY_REST_TOOL_NAME,
    CHAT_SEND_PATH,
    MATCHING_PANEL_ME_PATH,
    MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
    RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
    RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
    SUPPORT_TASK_ACTION_PATH,
    build_all_rest_tool_definitions,
    build_chat_reply_rest_tool_definition,
    build_message_reply_suggestion_rest_tool_definition,
    build_retrieve_management_permissions_rest_tool_definition,
    build_retrieve_past_messages_rest_tool_definition,
    ensure_rest_tool_definitions,
    sync_rest_tool_definitions,
)
from open_chat.tool_definitions_management import (
    GET_USER_DETAIL_REST_TOOL_NAME,
    LIST_USER_FILTERS_REST_TOOL_NAME,
    MANAGEMENT_GET_TOOL_SPECS,
    MANAGEMENT_REST_TOOL_NAMES,
    QUERY_MATCHES_REST_TOOL_NAME,
    QUERY_USERS_REST_TOOL_NAME,
    USERS_DETAIL_PATH,
    USERS_FILTERS_PATH,
    USERS_LIST_PATH,
    build_mgmt_get_rest_tool_definition,
)

_CORE_REST_TOOL_NAMES = (
    CHAT_REPLY_REST_TOOL_NAME,
    MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME,
    RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
    RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
)
_ALL_REST_TOOL_NAMES = (*_CORE_REST_TOOL_NAMES, *MANAGEMENT_REST_TOOL_NAMES)


class RestToolDefinitionTests(SimpleTestCase):
    def test_build_chat_reply_rest_tool_definition(self):
        definition = build_chat_reply_rest_tool_definition("https://app.example.com").build()

        self.assertEqual(definition["name"], CHAT_REPLY_REST_TOOL_NAME)
        self.assertEqual(definition["operation_id"], "api_messages_send_create")
        self.assertEqual(definition["base_url_source"], "init")
        self.assertEqual(definition["base_url_input_name"], "api_host")

        openapi = json.loads(definition["openapi_source"])
        self.assertEqual(openapi["servers"], [{"url": "https://app.example.com"}])
        self.assertIn(CHAT_SEND_PATH, openapi["paths"])

        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertEqual(binding_inputs, {"chat_uuid", "cookie_header", "csrf_token", "message"})
        self.assertEqual(definition["safety_policy"]["allow_hosts"], ["app.example.com"])

    def test_build_message_reply_suggestion_rest_tool_definition(self):
        definition = build_message_reply_suggestion_rest_tool_definition("https://app.example.com").build()

        self.assertEqual(definition["name"], MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME)
        self.assertEqual(definition["operation_id"], "api_support_task_action_partial_update")

        openapi = json.loads(definition["openapi_source"])
        self.assertIn(SUPPORT_TASK_ACTION_PATH, openapi["paths"])
        operation = openapi["paths"][SUPPORT_TASK_ACTION_PATH]["patch"]
        self.assertIn("requestBody", operation)

        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertEqual(binding_inputs, {"task_pk", "cookie_header", "csrf_token", "parameters"})
        self.assertIn(
            "PatchedSupportTaskActionUpdateRequest",
            json.loads(definition["openapi_source"])["components"]["schemas"],
        )

    def test_build_retrieve_past_messages_rest_tool_definition(self):
        definition = build_retrieve_past_messages_rest_tool_definition("https://app.example.com").build()

        self.assertEqual(definition["name"], RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME)
        self.assertEqual(definition["operation_id"], "api_messages_list_2")

        openapi = json.loads(definition["openapi_source"])
        self.assertEqual(openapi["servers"], [{"url": "https://app.example.com"}])
        self.assertIn(CHAT_MESSAGES_LIST_PATH, openapi["paths"])

        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertEqual(binding_inputs, {"chat_uuid", "cookie_header", "csrf_token", "page", "page_size"})
        self.assertEqual(definition["safety_policy"]["allow_hosts"], ["app.example.com"])

    def test_build_retrieve_management_permissions_rest_tool_definition(self):
        definition = build_retrieve_management_permissions_rest_tool_definition("https://app.example.com").build()

        self.assertEqual(definition["name"], RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME)
        self.assertEqual(definition["operation_id"], "api_matching_me_retrieve")

        openapi = json.loads(definition["openapi_source"])
        self.assertIn(MATCHING_PANEL_ME_PATH, openapi["paths"])

        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertEqual(binding_inputs, {"cookie_header", "csrf_token"})

    def test_build_mgmt_list_user_filters_rest_tool_definition(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == LIST_USER_FILTERS_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertEqual(definition["name"], LIST_USER_FILTERS_REST_TOOL_NAME)
        openapi = json.loads(definition["openapi_source"])
        self.assertIn(USERS_FILTERS_PATH, openapi["paths"])
        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertEqual(binding_inputs, {"cookie_header", "csrf_token"})

    def test_build_mgmt_query_users_rest_tool_definition(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == QUERY_USERS_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertEqual(definition["name"], QUERY_USERS_REST_TOOL_NAME)
        self.assertIn("/matching/users/?", definition["description"])
        openapi = json.loads(definition["openapi_source"])
        self.assertIn(USERS_LIST_PATH, openapi["paths"])
        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertIn("list", binding_inputs)
        self.assertIn("search", binding_inputs)
        self.assertIn("page", binding_inputs)
        self.assertIn("page_size", binding_inputs)
        self.assertEqual(definition["safety_policy"]["timeout_seconds"], 30)
        self.assertEqual(definition["safety_policy"]["max_response_body_bytes"], 512_000)

    def test_build_mgmt_query_matches_rest_tool_definition_includes_panel_link(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == QUERY_MATCHES_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertIn("/matching/matches/?", definition["description"])

    def test_build_mgmt_get_user_detail_rest_tool_definition(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == GET_USER_DETAIL_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertEqual(definition["name"], GET_USER_DETAIL_REST_TOOL_NAME)
        openapi = json.loads(definition["openapi_source"])
        self.assertIn(USERS_DETAIL_PATH, openapi["paths"])
        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertIn("id", binding_inputs)

    def test_build_all_rest_tool_definitions(self):
        definitions = build_all_rest_tool_definitions()
        self.assertEqual([definition.build()["name"] for definition in definitions], list(_ALL_REST_TOOL_NAMES))
        self.assertEqual(len(definitions), 32)

    def test_sync_rest_tool_definitions_creates_missing_tools(self):
        client = MagicMock()
        client.list_dynamic_rest_tools.return_value = []
        result = sync_rest_tool_definitions(client, reload=False)
        self.assertEqual(result["created"], list(_ALL_REST_TOOL_NAMES))
        self.assertEqual(result["updated"], [])
        self.assertEqual(client.save_dynamic_rest_tool.call_count, len(_ALL_REST_TOOL_NAMES))

    def test_sync_rest_tool_definitions_reload(self):
        client = MagicMock()
        client.list_dynamic_rest_tools.return_value = [{"name": name} for name in _CORE_REST_TOOL_NAMES]
        result = sync_rest_tool_definitions(client, reload=True)
        self.assertEqual(result["deleted"], sorted(_CORE_REST_TOOL_NAMES))
        self.assertEqual(result["created"], list(_ALL_REST_TOOL_NAMES))
        self.assertEqual(client.delete_dynamic_rest_tool.call_count, len(_CORE_REST_TOOL_NAMES))
        self.assertEqual(client.save_dynamic_rest_tool.call_count, len(_ALL_REST_TOOL_NAMES))

    def test_ensure_rest_tool_definitions_creates_only_missing_tools(self):
        client = MagicMock()
        client.list_dynamic_rest_tools.return_value = [
            {"name": CHAT_REPLY_REST_TOOL_NAME},
            {"name": MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME},
        ]
        result = ensure_rest_tool_definitions(client)
        self.assertEqual(
            result["created"],
            [
                RETRIEVE_PAST_MESSAGES_REST_TOOL_NAME,
                RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
                *MANAGEMENT_REST_TOOL_NAMES,
            ],
        )
        self.assertEqual(
            result["updated"], sorted([CHAT_REPLY_REST_TOOL_NAME, MESSAGE_REPLY_SUGGESTION_REST_TOOL_NAME])
        )
        self.assertEqual(client.save_dynamic_rest_tool.call_count, len(_ALL_REST_TOOL_NAMES))
