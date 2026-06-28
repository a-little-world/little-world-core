from client import RESTToolBuilder, reduce_openapi_to_endpoint
from django.test import SimpleTestCase

from open_chat.rest_tool_schema import SESSION_AUTH_HEADER_PARAMS, bind_openapi_call_params, spectacular_schema
from open_chat.tool_definitions import CHAT_SEND_PATH, SUPPORT_TASK_ACTION_PATH
from open_chat.tool_definitions_management import QUERY_USERS_REST_TOOL_NAME, USERS_LIST_PATH


class RestToolSchemaTests(SimpleTestCase):
    def test_reduce_openapi_to_endpoint_for_chat_send(self):
        operation_id, openapi_doc = reduce_openapi_to_endpoint(
            spectacular_schema(),
            path=CHAT_SEND_PATH,
            method="post",
            info_title="Test Chat Send API",
            extra_parameters=SESSION_AUTH_HEADER_PARAMS,
        )

        self.assertEqual(operation_id, "api_messages_send_create")
        self.assertIn(CHAT_SEND_PATH, openapi_doc["paths"])
        operation = openapi_doc["paths"][CHAT_SEND_PATH]["post"]
        header_names = {param["name"] for param in operation["parameters"] if param["in"] == "header"}
        self.assertIn("Cookie", header_names)
        self.assertIn("SendMessage", openapi_doc["components"]["schemas"])
        self.assertNotIn("responses", operation)

    def test_reduce_openapi_to_endpoint_with_request_body_override(self):
        request_body = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {"parameters": {"type": "object"}},
                    }
                }
            },
        }
        operation_id, openapi_doc = reduce_openapi_to_endpoint(
            spectacular_schema(),
            path=SUPPORT_TASK_ACTION_PATH,
            method="patch",
            info_title="Test Support Task Action API",
            request_body=request_body,
        )

        self.assertEqual(operation_id, "api_support_task_action_partial_update")
        operation = openapi_doc["paths"][SUPPORT_TASK_ACTION_PATH]["patch"]
        self.assertEqual(operation["requestBody"], request_body)

    def test_reduce_openapi_to_endpoint_collects_request_body_refs(self):
        _operation_id, openapi_doc = reduce_openapi_to_endpoint(
            spectacular_schema(),
            path=SUPPORT_TASK_ACTION_PATH,
            method="patch",
            info_title="Test Support Task Action API",
        )

        schemas = openapi_doc["components"]["schemas"]
        self.assertIn("PatchedSupportTaskActionUpdateRequest", schemas)
        self.assertIn("parameters", schemas["PatchedSupportTaskActionUpdateRequest"]["properties"])

    def test_bind_openapi_call_params_for_users_list(self):
        operation_id, reduced_doc = reduce_openapi_to_endpoint(
            spectacular_schema(),
            path=USERS_LIST_PATH,
            method="get",
            info_title="Test Users List API",
            extra_parameters=SESSION_AUTH_HEADER_PARAMS,
        )
        self.assertTrue(operation_id)
        builder = (
            RESTToolBuilder(QUERY_USERS_REST_TOOL_NAME, "test")
            .openapi_inline(reduced_doc)
            .operation(operation_id)
            .bind_session_auth()
        )
        builder = bind_openapi_call_params(builder, reduced_doc, USERS_LIST_PATH, "get")
        definition = builder.build()
        binding_inputs = {binding["input_name"] for binding in definition["param_bindings"]}
        self.assertIn("list", binding_inputs)
        self.assertIn("search", binding_inputs)
        self.assertIn("page", binding_inputs)
        self.assertNotIn("Cookie", binding_inputs)
        self.assertNotIn("X-CSRFToken", binding_inputs)
