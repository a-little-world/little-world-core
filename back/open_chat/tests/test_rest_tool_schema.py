from django.test import SimpleTestCase

from open_chat.rest_tool_schema import build_openapi_document_template
from open_chat.tool_definitions import (
    CHAT_SEND_PATH,
    SUPPORT_TASK_ACTION_PATH,
)


class RestToolSchemaTests(SimpleTestCase):
    def test_build_openapi_document_template_for_chat_send(self):
        operation_id, openapi_doc = build_openapi_document_template(
            path=CHAT_SEND_PATH,
            method="post",
            info_title="Test Chat Send API",
            extra_parameters=[
                {
                    "in": "header",
                    "name": "Cookie",
                    "required": True,
                    "schema": {"type": "string"},
                }
            ],
            component_schema_names=("SendMessage",),
        )

        self.assertEqual(operation_id, "api_messages_send_create")
        self.assertIn(CHAT_SEND_PATH, openapi_doc["paths"])
        operation = openapi_doc["paths"][CHAT_SEND_PATH]["post"]
        header_names = {param["name"] for param in operation["parameters"] if param["in"] == "header"}
        self.assertIn("Cookie", header_names)
        self.assertIn("SendMessage", openapi_doc["components"]["schemas"])

    def test_build_openapi_document_template_with_request_body_override(self):
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
        operation_id, openapi_doc = build_openapi_document_template(
            path=SUPPORT_TASK_ACTION_PATH,
            method="patch",
            info_title="Test Support Task Action API",
            request_body=request_body,
        )

        self.assertEqual(operation_id, "api_support_task_action_partial_update")
        operation = openapi_doc["paths"][SUPPORT_TASK_ACTION_PATH]["patch"]
        self.assertEqual(operation["requestBody"], request_body)
