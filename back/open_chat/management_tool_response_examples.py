"""Trust checks for Open Chat management REST tool response examples.

Response examples are documented on management API endpoints via drf-spectacular
``@extend_schema(responses=...)`` on each view, using serializers and pagination classes.
Open Chat reads them through ``open_chat.openapi_response_examples``.
"""

from __future__ import annotations

from typing import Any

USERS_FILTERS_PATH = "/api/matching/users/filters/"
MATCHES_FILTERS_PATH = "/api/matching/matches/filters/"
VIDEO_CALLS_FILTERS_PATH = "/api/matching/video_calls/filters/"
SCORES_FILTERS_PATH = "/api/matching/scores/filters/"
DYNAMIC_USER_LISTS_PATH = "/api/dynamic_user_lists/"
DYNAMIC_USER_LIST_DETAIL_PATH = "/api/dynamic_user_lists/{id}/"
SUPPORT_TASK_LIST_PATH = "/api/support_task/"
SUPPORT_TASK_DETAIL_PATH = "/api/support_task/{id}/"
SUPPORT_TASK_STATS_PATH = "/api/support_task/stats/"
SUPPORT_TASK_USER_SEARCH_PATH = "/api/support_task/user_search/"
SUPPORT_TASK_ASSIGNEE_USERS_PATH = "/api/support_task/assignee_users/"
USERS_DETAIL_PATH = "/api/matching/users/{id}/"
MATCHES_DETAIL_PATH = "/api/matching/matches/{id}/"
USERS_MESSAGES_PATH = "/api/matching/users/{id}/messages/"
USERS_TASKS_PATH = "/api/matching/users/{id}/tasks/"
USERS_NOTES_PATH = "/api/matching/users/{id}/notes/"
USERS_MATCH_WAITING_TIME_PATH = "/api/matching/users/{id}/match_waiting_time/"
USERS_PREMATCHING_APPOINTMENT_PATH = "/api/matching/users/{id}/prematching_appointment/"
USERS_SMS_PATH = "/api/matching/users/{id}/sms/"
USERS_EMAILS_PATH = "/api/matching/users/{id}/emails/"
MATCHES_NOTES_PATH = "/api/matching/matches/{id}/notes/"


def management_tool_response_example(path: str) -> Any | None:
    return None


def swagger_example_is_trustworthy(path: str, example: Any) -> bool:
    if example is None:
        return False

    if path.endswith("/filters/"):
        return isinstance(example, dict) and "filters" in example and "lists" in example

    if path == SUPPORT_TASK_STATS_PATH:
        return isinstance(example, dict) and {"NEW", "IN_PROGRESS", "COMPLETED"}.issubset(example.keys())

    if path in {SUPPORT_TASK_ASSIGNEE_USERS_PATH, SUPPORT_TASK_USER_SEARCH_PATH, DYNAMIC_USER_LIST_DETAIL_PATH}:
        return isinstance(example, list)

    if path == DYNAMIC_USER_LISTS_PATH:
        return isinstance(example, list)

    if path in {USERS_NOTES_PATH, MATCHES_NOTES_PATH}:
        return isinstance(example, str)

    if path == USERS_TASKS_PATH:
        return isinstance(example, list)

    if path == USERS_SMS_PATH:
        return isinstance(example, list)

    if path == USERS_MESSAGES_PATH:
        return isinstance(example, dict) and "chat" in example and "messages" in example

    if path in {SUPPORT_TASK_LIST_PATH, USERS_EMAILS_PATH}:
        return isinstance(example, dict) and "results" in example

    if path == SUPPORT_TASK_DETAIL_PATH:
        return isinstance(example, dict) and "title" in example and "status" in example

    if path in {USERS_DETAIL_PATH, MATCHES_DETAIL_PATH}:
        return isinstance(example, dict) and "id" in example

    if path == USERS_MATCH_WAITING_TIME_PATH:
        return isinstance(example, dict) and "waiting_time_string" in example

    if isinstance(example, dict) and "results" in example:
        row = example["results"][0] if example.get("results") else {}
        if path == "/api/matching/users/" and isinstance(row, dict):
            profile = row.get("profile")
            return isinstance(profile, dict) and "first_name" in profile and "interests" not in profile
        return True

    if isinstance(example, dict):
        if path == USERS_DETAIL_PATH:
            profile = example.get("profile")
            return isinstance(profile, dict) and "interests" in profile
        return any(key in example for key in ("id", "uuid", "title", "email"))

    return True
