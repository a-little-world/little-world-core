"""Documented response-shape examples for management REST tools.

drf-spectacular often omits or mis-documents custom actions and function views.
We prefer OpenAPI-derived samples when they match the real payload shape, and fall
back to these examples otherwise.
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
SUPPORT_TASK_STAFF_USERS_PATH = "/api/support_task/staff_users/"
USERS_MESSAGES_PATH = "/api/matching/users/{id}/messages/"
USERS_TASKS_PATH = "/api/matching/users/{id}/tasks/"
USERS_NOTES_PATH = "/api/matching/users/{id}/notes/"
USERS_MATCH_WAITING_TIME_PATH = "/api/matching/users/{id}/match_waiting_time/"
USERS_PREMATCHING_APPOINTMENT_PATH = "/api/matching/users/{id}/prematching_appointment/"
USERS_SMS_PATH = "/api/matching/users/{id}/sms/"
USERS_EMAILS_PATH = "/api/matching/users/{id}/emails/"
MATCHES_NOTES_PATH = "/api/matching/matches/{id}/notes/"

_FILTER_LIST_EXAMPLE = {
    "filters": [
        {
            "name": "state__email_authenticated",
            "filter_type": "BooleanFilter",
            "description": "Filter for users that have authenticated their email",
            "value_type": "boolean",
            "nullable": False,
        }
    ],
    "lists": [
        {"slug": "all", "name": "All users", "description": "Every user in scope"},
        {"slug": "needs_matching", "name": "Needs matching", "description": "Users waiting for a match"},
    ],
}

_PAGINATED_SHELL = {
    "page_size": 5,
    "pages_total": 3,
    "items_total": 12,
    "results_total": 12,
    "page": 1,
    "first_page": 1,
    "last_page": 3,
    "next_page": 2,
    "previous_page": None,
}

MANAGEMENT_TOOL_RESPONSE_EXAMPLES: dict[str, Any] = {
    USERS_FILTERS_PATH: _FILTER_LIST_EXAMPLE,
    MATCHES_FILTERS_PATH: _FILTER_LIST_EXAMPLE,
    VIDEO_CALLS_FILTERS_PATH: {
        "filters": [
            {
                "name": "created_between",
                "filter_type": "DateFromToRangeFilter",
                "description": "Range filter for created timestamp",
                "value_type": "string",
                "nullable": False,
            }
        ],
        "lists": [],
    },
    SCORES_FILTERS_PATH: _FILTER_LIST_EXAMPLE,
    DYNAMIC_USER_LISTS_PATH: [
        {"id": 1, "name": "VIP learners", "description": "Manual shortlist", "users": [10, 11]},
    ],
    DYNAMIC_USER_LIST_DETAIL_PATH: [
        {"id": 10, "email": "learner@example.com"},
        {"id": 11, "email": "volunteer@example.com"},
    ],
    SUPPORT_TASK_LIST_PATH: {
        **_PAGINATED_SHELL,
        "results": [
            {
                "id": 42,
                "title": "Reply to chat message",
                "status": "NEW",
                "priority": "MEDIUM",
                "related_user_profile": {"id": 10, "email": "learner@example.com"},
            }
        ],
    },
    SUPPORT_TASK_DETAIL_PATH: {
        "id": 42,
        "title": "Reply to chat message",
        "description": "",
        "status": "NEW",
        "priority": "MEDIUM",
        "action": {"action_type": "support_reply", "status": "OPEN", "parameters": {"message": ""}},
    },
    SUPPORT_TASK_STATS_PATH: {"NEW": 3, "IN_PROGRESS": 1, "COMPLETED": 42},
    SUPPORT_TASK_USER_SEARCH_PATH: [
        {
            "id": 10,
            "email": "learner@example.com",
            "first_name": "Alex",
            "second_name": "Example",
        }
    ],
    SUPPORT_TASK_STAFF_USERS_PATH: [
        {"id": 1, "email": "staff@example.com", "first_name": "Support", "last_name": "Agent"},
    ],
    USERS_MESSAGES_PATH: {
        "chat": {"uuid": "c9eec680-b88a-41e0-9ba6-5e00f9b2ff15", "partner": "bot@example.com"},
        "messages": {
            **_PAGINATED_SHELL,
            "results": [
                {
                    "uuid": "msg-uuid",
                    "sender": "user-uuid",
                    "created": "2026-06-28T12:00:00Z",
                    "text": "Hello",
                    "read": False,
                }
            ],
        },
    },
    USERS_TASKS_PATH: [
        {
            "id": 7,
            "description": "Follow up on onboarding",
            "state": "OPEN",
            "created_at": "2026-06-28T12:00:00Z",
        }
    ],
    USERS_NOTES_PATH: "Internal note about the user.",
    USERS_MATCH_WAITING_TIME_PATH: {
        "waiting_since": "2026-06-01T08:00:00Z",
        "days_waiting": 27,
    },
    USERS_PREMATCHING_APPOINTMENT_PATH: {
        "id": 5,
        "start_time": "2026-06-28T14:00:00Z",
        "end_time": "2026-06-28T14:30:00Z",
        "status": "scheduled",
    },
    USERS_SMS_PATH: [
        {
            "id": 1,
            "message": "Reminder sent",
            "created_at": "2026-06-28T12:00:00Z",
            "status": "sent",
        }
    ],
    USERS_EMAILS_PATH: {
        **_PAGINATED_SHELL,
        "results": [
            {
                "id": 99,
                "subject": "Welcome to Little World",
                "time": "2026-06-28T12:00:00Z",
                "status": "sent",
            }
        ],
    },
    MATCHES_NOTES_PATH: "Internal note about the match.",
}


def management_tool_response_example(path: str) -> Any | None:
    return MANAGEMENT_TOOL_RESPONSE_EXAMPLES.get(path)


def swagger_example_is_trustworthy(path: str, example: Any) -> bool:
    if example is None:
        return False

    if path.endswith("/filters/"):
        return isinstance(example, dict) and "filters" in example and "lists" in example

    if path == SUPPORT_TASK_STATS_PATH:
        return isinstance(example, dict) and {"NEW", "IN_PROGRESS", "COMPLETED"}.issubset(example.keys())

    if path in {SUPPORT_TASK_STAFF_USERS_PATH, SUPPORT_TASK_USER_SEARCH_PATH, DYNAMIC_USER_LIST_DETAIL_PATH}:
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

    if path in {SUPPORT_TASK_LIST_PATH, USERS_EMAILS_PATH} or path.endswith("/") and "Paginated" in str(example):
        return isinstance(example, dict) and "results" in example

    if path == SUPPORT_TASK_DETAIL_PATH:
        return isinstance(example, dict) and "title" in example and "status" in example

    if isinstance(example, dict) and "results" in example:
        return True

    if isinstance(example, dict):
        return any(key in example for key in ("id", "uuid", "title", "email"))

    return True
