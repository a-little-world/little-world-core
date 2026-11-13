import json

from django.test import SimpleTestCase

from open_chat.management_tool_response_examples import swagger_example_is_trustworthy
from open_chat.openapi_response_examples import (
    append_output_example_to_description,
    describe_openapi_response_example,
    extract_openapi_response_example,
    format_openapi_response_example,
)
from open_chat.rest_tool_schema import spectacular_schema
from open_chat.tool_definitions_management import (
    GET_SUPPORT_TASK_STATS_REST_TOOL_NAME,
    LIST_USER_FILTERS_REST_TOOL_NAME,
    MANAGEMENT_GET_TOOL_SPECS,
    QUERY_USERS_REST_TOOL_NAME,
    SUPPORT_TASK_STATS_PATH,
    USERS_DETAIL_PATH,
    USERS_FILTERS_PATH,
    USERS_LIST_PATH,
    build_mgmt_get_rest_tool_definition,
)


class OpenApiResponseExampleTests(SimpleTestCase):
    def test_extract_users_filters_response_example_from_openapi(self):
        rendered = describe_openapi_response_example(
            spectacular_schema(),
            path=USERS_FILTERS_PATH,
            method="get",
            fallback=None,
            trust_example=swagger_example_is_trustworthy,
        )

        self.assertIsNotNone(rendered)
        parsed = json.loads(rendered)
        self.assertIn("filters", parsed)
        self.assertIn("lists", parsed)

    def test_swagger_example_is_trustworthy_for_filters_path(self):
        example = extract_openapi_response_example(
            spectacular_schema(),
            path=USERS_FILTERS_PATH,
            method="get",
        )
        self.assertTrue(swagger_example_is_trustworthy(USERS_FILTERS_PATH, example))

    def test_extract_query_users_response_example_has_table_profile_without_interests(self):
        example = extract_openapi_response_example(
            spectacular_schema(),
            path=USERS_LIST_PATH,
            method="get",
        )

        self.assertIsInstance(example, dict)
        self.assertIn("results", example)
        self.assertIn("items_total", example)
        self.assertLessEqual(len(example["results"]), 1)
        if example["results"]:
            profile = example["results"][0].get("profile", {})
            self.assertIn("first_name", profile)
            self.assertNotIn("interests", profile)

    def test_extract_user_detail_response_example_includes_profile_interests(self):
        example = extract_openapi_response_example(
            spectacular_schema(),
            path=USERS_DETAIL_PATH,
            method="get",
        )

        self.assertIsInstance(example, dict)
        self.assertIn("interests", example.get("profile", {}))

    def test_extract_support_task_stats_response_example(self):
        rendered = describe_openapi_response_example(
            spectacular_schema(),
            path=SUPPORT_TASK_STATS_PATH,
            method="get",
            fallback=None,
            trust_example=swagger_example_is_trustworthy,
        )

        parsed = json.loads(rendered)
        self.assertIn("NEW", parsed)
        self.assertIn("IN_PROGRESS", parsed)
        self.assertIn("COMPLETED", parsed)

    def test_format_openapi_response_example_truncates_long_payload(self):
        rendered = format_openapi_response_example({"items": ["x" * 2000]}, max_length=100)
        self.assertTrue(rendered.endswith("..."))
        self.assertLessEqual(len(rendered), 100)

    def test_append_output_example_to_description(self):
        description = append_output_example_to_description(
            "List users.",
            '{"results":[],"items_total":1}',
        )
        self.assertIn("Example JSON response:", description)
        self.assertIn('"items_total":1', description)

    def test_describe_openapi_response_example_returns_json_text(self):
        rendered = describe_openapi_response_example(
            spectacular_schema(),
            path=SUPPORT_TASK_STATS_PATH,
            method="get",
            fallback=None,
            trust_example=swagger_example_is_trustworthy,
        )
        self.assertIsNotNone(rendered)
        parsed = json.loads(rendered)
        self.assertIn("NEW", parsed)


class ManagementToolDescriptionExampleTests(SimpleTestCase):
    def test_build_mgmt_tool_description_includes_output_example(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == LIST_USER_FILTERS_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertIn("Example JSON response:", definition["description"])
        self.assertIn('"filters"', definition["description"])
        self.assertIn('"lists"', definition["description"])

    def test_build_mgmt_query_users_description_includes_pagination_example(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == QUERY_USERS_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertIn("Example JSON response:", definition["description"])
        self.assertIn('"results"', definition["description"])
        self.assertIn('"items_total"', definition["description"])

    def test_build_mgmt_support_task_stats_description_includes_status_counts(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == GET_SUPPORT_TASK_STATS_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()

        self.assertIn("Example JSON response:", definition["description"])
        self.assertIn('"NEW"', definition["description"])
        self.assertIn('"IN_PROGRESS"', definition["description"])
