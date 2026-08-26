"""Live integration checks for management REST tools and Open Chat interactions."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.test import Client
from management.models.user import User

from open_chat.basic_chat_interaction import CHAT_REPLY_BOT
from open_chat.helpers import (
    build_open_chat_client,
    build_session_tool_init_payload,
    build_tool_session_context,
    value_or,
)

if TYPE_CHECKING:
    from client import OpenChatClient
from open_chat.models import OpenChatConfiguration
from open_chat.tool_definitions import (
    RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
    sync_rest_tool_definitions,
)
from open_chat.tool_definitions_management import (
    GET_SUPPORT_TASK_STATS_REST_TOOL_NAME,
    GET_USER_DETAIL_REST_TOOL_NAME,
    LIST_DYNAMIC_USER_LISTS_REST_TOOL_NAME,
    LIST_MATCH_FILTERS_REST_TOOL_NAME,
    LIST_SCORE_FILTERS_REST_TOOL_NAME,
    LIST_SUPPORT_STAFF_REST_TOOL_NAME,
    LIST_USER_FILTERS_REST_TOOL_NAME,
    LIST_VIDEO_CALL_FILTERS_REST_TOOL_NAME,
    QUERY_MATCHES_REST_TOOL_NAME,
    QUERY_PREMATCHING_APPOINTMENTS_REST_TOOL_NAME,
    QUERY_SUPPORT_TASKS_REST_TOOL_NAME,
    QUERY_USERS_REST_TOOL_NAME,
    QUERY_VIDEO_CALLS_REST_TOOL_NAME,
    SUPPORT_TASK_USER_SEARCH_REST_TOOL_NAME,
)


@dataclass(frozen=True)
class ApiToolCase:
    tool_name: str
    method: str
    path: str
    query: dict[str, str] | None = None
    expect_key: str | None = None


@dataclass(frozen=True)
class InteractionToolCase:
    tool_name: str
    message: str


API_TOOL_CASES: tuple[ApiToolCase, ...] = (
    ApiToolCase(
        LIST_USER_FILTERS_REST_TOOL_NAME,
        "GET",
        "/api/matching/users/filters/",
        expect_key="lists",
    ),
    ApiToolCase(
        LIST_MATCH_FILTERS_REST_TOOL_NAME,
        "GET",
        "/api/matching/matches/filters/",
        expect_key="lists",
    ),
    ApiToolCase(
        LIST_VIDEO_CALL_FILTERS_REST_TOOL_NAME,
        "GET",
        "/api/matching/video_calls/filters/",
        expect_key="filters",
    ),
    ApiToolCase(
        LIST_SCORE_FILTERS_REST_TOOL_NAME,
        "GET",
        "/api/matching/scores/filters/",
        expect_key="filters",
    ),
    ApiToolCase(LIST_DYNAMIC_USER_LISTS_REST_TOOL_NAME, "GET", "/api/dynamic_user_lists/"),
    ApiToolCase(
        QUERY_USERS_REST_TOOL_NAME,
        "GET",
        "/api/matching/users/",
        query={"page_size": "1", "list": "all"},
        expect_key="items_total",
    ),
    ApiToolCase(
        QUERY_MATCHES_REST_TOOL_NAME,
        "GET",
        "/api/matching/matches/",
        query={"page_size": "1"},
        expect_key="items_total",
    ),
    ApiToolCase(
        QUERY_VIDEO_CALLS_REST_TOOL_NAME,
        "GET",
        "/api/matching/video_calls/",
        query={"page_size": "1"},
        expect_key="items_total",
    ),
    ApiToolCase(
        QUERY_SUPPORT_TASKS_REST_TOOL_NAME,
        "GET",
        "/api/support_task/",
        query={"page_size": "1"},
        expect_key="items_total",
    ),
    ApiToolCase(
        QUERY_PREMATCHING_APPOINTMENTS_REST_TOOL_NAME,
        "GET",
        "/api/matching/prematchingappointments/",
        query={"page_size": "1"},
        expect_key="items_total",
    ),
    ApiToolCase(
        GET_USER_DETAIL_REST_TOOL_NAME,
        "GET",
        "/api/matching/users/{id}/",
    ),
    ApiToolCase(
        GET_SUPPORT_TASK_STATS_REST_TOOL_NAME,
        "GET",
        "/api/support_task/stats/",
        expect_key="NEW",
    ),
    ApiToolCase(
        SUPPORT_TASK_USER_SEARCH_REST_TOOL_NAME,
        "GET",
        "/api/support_task/user_search/",
        query={"q": "tim"},
    ),
    ApiToolCase(LIST_SUPPORT_STAFF_REST_TOOL_NAME, "GET", "/api/support_task/staff_users/"),
    ApiToolCase(
        RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
        "GET",
        "/api/matching/me/",
        expect_key="email",
    ),
)

INTERACTION_TOOL_CASES: tuple[InteractionToolCase, ...] = (
    InteractionToolCase(
        LIST_USER_FILTERS_REST_TOOL_NAME,
        f"Call `{LIST_USER_FILTERS_REST_TOOL_NAME}` immediately with no arguments.",
    ),
    InteractionToolCase(
        QUERY_USERS_REST_TOOL_NAME,
        f"Call `{QUERY_USERS_REST_TOOL_NAME}` with list=all and page_size=1.",
    ),
    InteractionToolCase(
        QUERY_MATCHES_REST_TOOL_NAME,
        f"Call `{QUERY_MATCHES_REST_TOOL_NAME}` with page_size=1.",
    ),
    InteractionToolCase(
        GET_SUPPORT_TASK_STATS_REST_TOOL_NAME,
        f"Call `{GET_SUPPORT_TASK_STATS_REST_TOOL_NAME}`.",
    ),
    InteractionToolCase(
        RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME,
        f"Call `{RETRIEVE_MANAGEMENT_PERMISSIONS_REST_TOOL_NAME}`.",
    ),
)


def _single_tool_init(session_init: dict[str, str], tool_name: str) -> dict[str, dict[str, str]]:
    """Init payload for only the tool under test."""
    return {tool_name: dict(session_init)}


def _tool_call_entries(message: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for tc in message.get("tool_calls") or []:
        if isinstance(tc, dict):
            entries.append(tc)
        else:
            entries.append(
                {
                    "name": getattr(tc, "name", None),
                    "arguments": getattr(tc, "arguments", None),
                    "result": getattr(tc, "result", None),
                }
            )
    return entries


def _result_succeeded(result: str | None) -> bool:
    if not result:
        return False
    lowered = result.lower()
    if "failed with error" in lowered:
        return False
    if "not in allow_hosts" in lowered or "connection refused" in lowered or "connect:" in lowered:
        return False
    if any(code in result for code in ('"403"', '"401"', '"404"', " 403 ", " 401 ", " 404 ")):
        return False
    stripped = result.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return True
    if any(key in result for key in ('"lists"', '"filters"', '"items_total"', '"email"', '"NEW"')):
        return True
    return len(stripped) > 50 and "please continue" not in lowered


class Command(BaseCommand):
    help = "Run live API and Open Chat interaction checks for management REST tools."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-interactions",
            action="store_true",
            help="Only run direct Django API checks, skip Open Chat LLM interactions.",
        )
        parser.add_argument(
            "--skip-sync",
            action="store_true",
            help="Do not reload REST tool definitions on Open Chat before interaction tests.",
        )
        parser.add_argument(
            "--interaction-timeout",
            type=int,
            default=180,
            help="Seconds to wait for each Open Chat interaction.",
        )

    def handle(self, *args, **options):
        user = User.objects.filter(email=settings.MATCHING_USER_MAIL).first()
        if user is None:
            self.stderr.write(self.style.ERROR(f"Management user not found: {settings.MATCHING_USER_MAIL}"))
            return

        configuration = OpenChatConfiguration.objects.filter(user=user).first()
        if configuration is None:
            self.stderr.write(self.style.ERROR("OpenChatConfiguration missing for management user."))
            return

        session_id, csrf_token, api_host = build_tool_session_context(user)
        self.stdout.write(f"Actor: {user.email} (id={user.pk})")
        self.stdout.write(f"Open Chat tool api_host: {api_host}")
        if "host.docker.internal" not in api_host:
            self.stdout.write(
                self.style.WARNING(
                    "api_host is not host.docker.internal — Open Chat in Docker may not reach the backend. "
                    "Set OPEN_CHAT_TOOL_API_HOST or BASE_URL=http://localhost:8000."
                )
            )

        api_failures = self._run_api_cases(user, session_id, csrf_token)
        interaction_failures = 0
        if not options["skip_interactions"]:
            interaction_failures = self._run_interaction_cases(
                configuration=configuration,
                session_id=session_id,
                csrf_token=csrf_token,
                api_host=api_host,
                skip_sync=options["skip_sync"],
                timeout=options["interaction_timeout"],
            )

        total_failures = api_failures + interaction_failures
        if total_failures:
            self.stderr.write(self.style.ERROR(f"\n{total_failures} check(s) failed."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("\nAll management REST tool checks passed."))

    def _run_api_cases(self, user: User, session_id: str, csrf_token: str) -> int:
        self.stdout.write(self.style.MIGRATE_HEADING("\nDirect API checks (Django test client)"))
        client = Client()
        client.cookies["sessionid"] = session_id
        client.cookies["csrftoken"] = csrf_token
        failures = 0

        for case in API_TOOL_CASES:
            path = case.path
            if "{id}" in path:
                path = path.replace("{id}", user.email)

            if case.method == "GET":
                response = client.get(path, case.query or {}, HTTP_X_CSRFTOKEN=csrf_token)
            else:
                response = client.generic(case.method, path, HTTP_X_CSRFTOKEN=csrf_token)

            ok = response.status_code == 200
            detail = ""
            if ok and case.expect_key:
                try:
                    payload = json.loads(response.content)
                    keys = case.expect_key.split(".")
                    value: Any = payload
                    for key in keys:
                        value = value[key]
                    detail = f" ({case.expect_key}={value!r})" if value is not None else ""
                    ok = value is not None
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    ok = False
                    detail = f" (missing {case.expect_key}: {exc})"

            status = self.style.SUCCESS("PASS") if ok else self.style.ERROR("FAIL")
            self.stdout.write(f"  [{status}] {case.tool_name} -> {case.method} {path}{detail}")
            if not ok:
                failures += 1
                self.stdout.write(f"         status={response.status_code} body={response.content[:200]!r}")

        return failures

    def _run_interaction_cases(
        self,
        *,
        configuration: OpenChatConfiguration,
        session_id: str,
        csrf_token: str,
        api_host: str,
        skip_sync: bool,
        timeout: int,
    ) -> int:
        self.stdout.write(self.style.MIGRATE_HEADING("\nOpen Chat interaction checks (one tool per interaction)"))
        client = build_open_chat_client(configuration)
        client.login()

        if skip_sync:
            self.stdout.write("  Skipping REST tool sync (--skip-sync).")
        else:
            sync_result = sync_rest_tool_definitions(client, reload=True)
            self.stdout.write(f"  Synced tools (reload): created={len(sync_result['created'])}")

        session_init = build_session_tool_init_payload(
            api_host=api_host,
            session_id=session_id,
            csrf_token=csrf_token,
        )

        failures = 0
        for case in INTERACTION_TOOL_CASES:
            self.stdout.write(f"\n  Interaction for `{case.tool_name}` (tools: [{case.tool_name}])...")
            interaction = client.interact(
                bot=CHAT_REPLY_BOT,
                message=case.message,
                share=False,
                tool_init=_single_tool_init(session_init, case.tool_name),
            )
            uuid = str(interaction.uuid)
            self.stdout.write(f"    interaction_uuid={uuid}")

            finished = self._wait_for_interaction(client, uuid, timeout=timeout)
            tool_ok, details = self._evaluate_interaction(
                client,
                uuid,
                expected_tool=case.tool_name,
            )

            if not finished:
                self.stdout.write(self.style.WARNING("    timed out waiting for finished meta"))
            for line in details:
                self.stdout.write(f"    {line}")

            status = self.style.SUCCESS("PASS") if tool_ok else self.style.ERROR("FAIL")
            self.stdout.write(f"  [{status}] {case.tool_name}")
            if not tool_ok:
                failures += 1

        return failures

    def _wait_for_interaction(self, client: OpenChatClient, uuid: str, *, timeout: int) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            rows = value_or(client.list_interaction_messages(uuid, page=1, limit=50).rows, [])
            for row in rows:
                meta = row.to_dict().get("meta_data") or {}
                if meta.get("finished"):
                    return True
            time.sleep(3)
        return False

    def _evaluate_interaction(
        self,
        client: OpenChatClient,
        uuid: str,
        *,
        expected_tool: str,
    ) -> tuple[bool, list[str]]:
        rows = value_or(client.list_interaction_messages(uuid, page=1, limit=50).rows, [])
        details: list[str] = []
        tool_ok = False

        for row in rows:
            message = row.to_dict()
            if not message.get("sender_is_automated"):
                continue
            text = message.get("text") or ""
            if message.get("meta_data", {}).get("error"):
                details.append(f"bot error message: {text[:200]}")

            for tc in _tool_call_entries(message):
                name = str(tc.get("name") or "")
                result = tc.get("result")
                if isinstance(result, dict):
                    result = json.dumps(result)
                result_text = str(result or "")
                details.append(f"tool {name}: {result_text[:160]}")
                if name == expected_tool and _result_succeeded(result_text):
                    tool_ok = True

        return tool_ok, details
