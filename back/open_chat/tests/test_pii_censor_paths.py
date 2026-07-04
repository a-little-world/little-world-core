"""Tests that Open Chat REST tool response_censor_paths remove end-user PII."""

from __future__ import annotations

import copy
from typing import Any

from django.test import SimpleTestCase

from open_chat.tool_definitions import (
    build_retrieve_management_permissions_rest_tool_definition,
    build_retrieve_past_messages_rest_tool_definition,
)
from open_chat.tool_definitions_management import (
    _TOOLS_WITHOUT_PII_CENSOR,
    GET_MATCH_NOTES_REST_TOOL_NAME,
    GET_USER_DETAIL_REST_TOOL_NAME,
    GET_USER_NOTES_REST_TOOL_NAME,
    GET_USER_TASKS_REST_TOOL_NAME,
    MANAGEMENT_GET_TOOL_SPECS,
    _censor_paths_for_spec,
    build_mgmt_get_rest_tool_definition,
)

EXAMPLE_EMAIL = "learner.example@test.invalid"
EXAMPLE_PAST_EMAIL = "old.address@example.com"
EXAMPLE_FIRST_NAME = "Jane"
EXAMPLE_LAST_NAME = "Example"
EXAMPLE_PHONE = "+491234567890"

# Snapshot-shaped fixture mirroring AdvancedUserSerializer output (synthetic PII only).
USER_DETAIL_FIXTURE: dict[str, Any] = {
    "id": 42,
    "email": EXAMPLE_EMAIL,
    "profile": {
        "first_name": EXAMPLE_FIRST_NAME,
        "second_name": EXAMPLE_LAST_NAME,
        "phone_mobile": EXAMPLE_PHONE,
        "description": f"{EXAMPLE_FIRST_NAME} {EXAMPLE_LAST_NAME}\nExample bio text",
        "job_skill_description": "Example skills summary",
    },
    "state": {
        "past_emails": [EXAMPLE_PAST_EMAIL],
        "notes": f"Internal note mentioning {EXAMPLE_FIRST_NAME}",
        "email_auth_pin": 12345,
        "email_auth_hash": "00000000-0000-4000-8000-000000000001",
        "auto_login_api_token": "00000000-0000-4000-8000-000000000002",
        "prematch_booking_code": "00000000-0000-4000-8000-000000000003",
    },
    "matches": {
        "support": {
            "results": [
                {
                    "partner": {
                        "first_name": "Support Team",
                        "description": "Support team profile description",
                        "phone_mobile": "",
                    },
                    "chat": {
                        "partner": {
                            "first_name": "Support Team",
                            "description": "Support team profile description",
                        },
                        "newest_message": {
                            "text": f"Hello {EXAMPLE_FIRST_NAME},\nthanks for your message.",
                        },
                    },
                }
            ]
        }
    },
}


def remove_censored_path(node: Any, segments: list[str]) -> None:
    """Mirror of Open Chat Go removeCensoredPath (rest_api_tool_integration.go)."""
    if not segments:
        return
    segment = segments[0]
    last_segment = len(segments) == 1

    if isinstance(node, dict):
        if segment == "*":
            if last_segment:
                return
            for child in node.values():
                remove_censored_path(child, segments[1:])
            return
        if last_segment:
            node.pop(segment, None)
            return
        if segment in node:
            remove_censored_path(node[segment], segments[1:])
    elif isinstance(node, list):
        if segment == "*":
            if last_segment:
                return
            for child in node:
                remove_censored_path(child, segments[1:])


def apply_response_censor_paths(data: Any, censor_paths: tuple[str, ...]) -> Any:
    payload = copy.deepcopy(data)
    for path in censor_paths:
        remove_censored_path(payload, path.split("."))
    return payload


def find_email_like_strings(obj: Any, path: str = "") -> list[tuple[str, str]]:
    leaks: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}" if path else key
            leaks.extend(find_email_like_strings(value, child_path))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            leaks.extend(find_email_like_strings(value, f"{path}[{index}]"))
    elif isinstance(obj, str) and obj and "@" in obj:
        domain = obj.rsplit("@", 1)[-1]
        if "." in domain:
            leaks.append((path, obj))
    return leaks


class PiiCensorPathTests(SimpleTestCase):
    def test_get_user_detail_censor_removes_structured_pii(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == GET_USER_DETAIL_REST_TOOL_NAME)
        paths = _censor_paths_for_spec(spec)
        censored = apply_response_censor_paths(USER_DETAIL_FIXTURE, paths)

        self.assertNotIn("email", censored)
        self.assertNotIn("first_name", censored["profile"])
        self.assertNotIn("second_name", censored["profile"])
        self.assertNotIn("phone_mobile", censored["profile"])
        self.assertNotIn("past_emails", censored["state"])
        self.assertNotIn("email_auth_pin", censored["state"])

        email_leaks = find_email_like_strings(censored)
        self.assertEqual(email_leaks, [], msg=f"Email-like strings remain: {email_leaks}")

        # Profile description is censored (often contains full names); staff notes are kept.
        self.assertNotIn("description", censored["profile"])
        self.assertNotIn("job_skill_description", censored["profile"])
        self.assertIn("notes", censored["state"])
        self.assertIn(EXAMPLE_FIRST_NAME, censored["state"]["notes"])

        newest_message = censored["matches"]["support"]["results"][0]["chat"]["newest_message"]
        self.assertNotIn("text", newest_message)

    def test_get_user_detail_tool_definition_includes_expected_paths(self):
        spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == GET_USER_DETAIL_REST_TOOL_NAME)
        definition = build_mgmt_get_rest_tool_definition(spec, "https://app.example.com").build()
        censor_paths = definition["safety_policy"]["response_censor_paths"]

        self.assertIn("state.past_emails", censor_paths)
        self.assertIn("profile.first_name", censor_paths)
        self.assertIn("profile.description", censor_paths)
        self.assertIn("matches.*.results.*.chat.newest_message.text", censor_paths)
        self.assertNotIn("state.notes", censor_paths)

    def test_core_tools_have_message_and_identity_censor_paths(self):
        past_messages = build_retrieve_past_messages_rest_tool_definition("https://app.example.com").build()
        permissions = build_retrieve_management_permissions_rest_tool_definition("https://app.example.com").build()

        self.assertIn("results.*.text", past_messages["safety_policy"]["response_censor_paths"])
        for field in ("email", "first_name", "last_name"):
            self.assertIn(field, permissions["safety_policy"]["response_censor_paths"])

    def test_user_data_tools_have_censor_paths(self):
        for spec in MANAGEMENT_GET_TOOL_SPECS:
            paths = _censor_paths_for_spec(spec)
            if spec.name in _TOOLS_WITHOUT_PII_CENSOR:
                self.assertEqual(paths, (), msg=f"{spec.name} should not define censor paths")
                continue
            self.assertTrue(paths, msg=f"{spec.name} must define response_censor_paths")

    def test_internal_notes_and_tasks_tools_have_no_censor_paths(self):
        for tool_name in (
            GET_USER_NOTES_REST_TOOL_NAME,
            GET_MATCH_NOTES_REST_TOOL_NAME,
            GET_USER_TASKS_REST_TOOL_NAME,
        ):
            spec = next(item for item in MANAGEMENT_GET_TOOL_SPECS if item.name == tool_name)
            self.assertEqual(_censor_paths_for_spec(spec), ())

    def test_censor_simulation_matches_go_wildcard_behavior(self):
        payload = {
            "users": [
                {"email": "one@example.com", "profile": {"first_name": "One"}},
                {"email": "two@example.com", "profile": {"first_name": "Two"}},
            ]
        }
        censored = apply_response_censor_paths(payload, ("users.*.email",))
        self.assertNotIn("email", censored["users"][0])
        self.assertNotIn("email", censored["users"][1])
        self.assertIn("first_name", censored["users"][0]["profile"])
