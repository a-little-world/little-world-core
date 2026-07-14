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
    GET_MATCH_DETAIL_REST_TOOL_NAME,
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
        self.assertIn("message", definition["description"])
        self.assertNotIn("<a {", definition["description"])
        self.assertEqual(definition["base_url_source"], "init")
        self.assertEqual(definition["base_url_input_name"], "api_host")

        openapi = json.loads(definition["openapi_source"])
        self.assertEqual(openapi["servers"], [{"url": "https://app.example.com"}])
        self.assertIn(CHAT_SEND_PATH, openapi["paths"])

        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertEqual(binding_inputs, {"chat_uuid", "cookie_header", "csrf_token", "message"})
        self.assertNotIn("allow_hosts", definition["safety_policy"])
        self.assertTrue(definition["safety_policy"]["allow_private_ips"])

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
        self.assertNotIn("allow_hosts", definition["safety_policy"])
        self.assertTrue(definition["safety_policy"]["allow_private_ips"])

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
        self.assertIn("list_*_filters", definition["description"])
        self.assertIn("never JSON arrays", definition["description"])
        self.assertIn("profile__user_type=learner", definition["description"])
        self.assertIn("/matching/users/?", definition["description"])
        self.assertIn("/matching/user/", definition["description"])
        self.assertIn("?tab=chat", definition["description"])
        openapi = json.loads(definition["openapi_source"])
        self.assertIn(USERS_LIST_PATH, openapi["paths"])
        params = openapi["paths"][USERS_LIST_PATH]["get"]["parameters"]
        order_by = next(param for param in params if param["name"] == "order_by")
        self.assertEqual(order_by["schema"]["type"], "string")
        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertIn("list", binding_inputs)
        self.assertIn("search", binding_inputs)
        self.assertIn("page", binding_inputs)
        self.assertIn("page_size", binding_inputs)
        self.assertEqual(definition["safety_policy"]["timeout_seconds"], 30)
        self.assertEqual(definition["safety_policy"]["max_response_body_bytes"], 512_000)

    def test_build_mgmt_query_users_rest_tool_definition_includes_interests_hint(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == QUERY_USERS_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertIn("profile.interests", definition["description"])
        self.assertIn("get_user_detail", definition["description"])
        self.assertIn("/matching/user/", definition["description"])
        self.assertIn("never `/matching/users/?search=", definition["description"])

    def test_build_mgmt_query_matches_rest_tool_definition_includes_panel_link(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == QUERY_MATCHES_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertIn("/matching/matches/?", definition["description"])

    def test_build_mgmt_get_user_detail_rest_tool_definition(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == GET_USER_DETAIL_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertEqual(definition["name"], GET_USER_DETAIL_REST_TOOL_NAME)
        self.assertIn("interests", definition["description"])
        self.assertIn("`id`", definition["description"])
        openapi = json.loads(definition["openapi_source"])
        self.assertIn(USERS_DETAIL_PATH, openapi["paths"])
        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertIn("id", binding_inputs)
        censor_paths = definition["safety_policy"]["response_censor_paths"]
        self.assertIn("email", censor_paths)
        self.assertIn("profile.first_name", censor_paths)
        self.assertIn("profile.second_name", censor_paths)
        self.assertIn("state.past_emails", censor_paths)
        self.assertIn("profile.description", censor_paths)
        self.assertIn("matches.*.results.*.chat.newest_message.text", censor_paths)
        self.assertNotIn("state.notes", censor_paths)
        self.assertIn("/matching/user/", definition["description"])

    def test_build_mgmt_query_users_censors_pii_in_paginated_results(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == QUERY_USERS_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        censor_paths = definition["safety_policy"]["response_censor_paths"]
        self.assertIn("results.*.email", censor_paths)
        self.assertIn("results.*.profile.first_name", censor_paths)
        self.assertIn("results.*.profile.second_name", censor_paths)
        self.assertIn("results.*.state.past_emails", censor_paths)
        self.assertIn("results.*.profile.description", censor_paths)

    def test_build_mgmt_query_matches_censors_participant_pii(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == QUERY_MATCHES_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        censor_paths = definition["safety_policy"]["response_censor_paths"]
        self.assertIn("results.*.user1.email", censor_paths)
        self.assertIn("results.*.user2.profile.second_name", censor_paths)

    def test_build_mgmt_list_user_filters_has_no_response_censor_paths(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == LIST_USER_FILTERS_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertNotIn("response_censor_paths", definition["safety_policy"])

    def test_build_mgmt_get_match_detail_rest_tool_definition(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == GET_MATCH_DETAIL_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertEqual(definition["name"], GET_MATCH_DETAIL_REST_TOOL_NAME)
        self.assertIn("`id`", definition["description"])
        self.assertIn("uuid", definition["description"])

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
