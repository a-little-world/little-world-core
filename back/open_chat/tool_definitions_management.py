from dataclasses import dataclass

from client import RESTToolBuilder, reduce_openapi_to_endpoint

from open_chat.rest_tool_schema import (
    API_HOST_INIT_FIELD,
    SESSION_AUTH_HEADER_PARAMS,
    allow_local_tool_hosts,
    bind_openapi_call_params,
    resolve_api_host,
    spectacular_schema,
)

# Path constants
USERS_LIST_PATH = "/api/matching/users/"
USERS_FILTERS_PATH = "/api/matching/users/filters/"
USERS_DETAIL_PATH = "/api/matching/users/{id}/"
USERS_MESSAGES_PATH = "/api/matching/users/{id}/messages/"
USERS_TASKS_PATH = "/api/matching/users/{id}/tasks/"
USERS_NOTES_PATH = "/api/matching/users/{id}/notes/"
USERS_MATCH_WAITING_TIME_PATH = "/api/matching/users/{id}/match_waiting_time/"
USERS_PREMATCHING_APPOINTMENT_PATH = "/api/matching/users/{id}/prematching_appointment/"
USERS_SMS_PATH = "/api/matching/users/{id}/sms/"
USERS_EMAILS_PATH = "/api/matching/users/{id}/emails/"

MATCHES_LIST_PATH = "/api/matching/matches/"
MATCHES_FILTERS_PATH = "/api/matching/matches/filters/"
MATCHES_DETAIL_PATH = "/api/matching/matches/{id}/"
MATCHES_NOTES_PATH = "/api/matching/matches/{id}/notes/"

VIDEO_CALLS_LIST_PATH = "/api/matching/video_calls/"
VIDEO_CALLS_FILTERS_PATH = "/api/matching/video_calls/filters/"
VIDEO_CALLS_DETAIL_PATH = "/api/matching/video_calls/{id}/"

SCORES_LIST_PATH = "/api/matching/scores/"
SCORES_FILTERS_PATH = "/api/matching/scores/filters/"
SCORES_DETAIL_PATH = "/api/matching/scores/{id}/"

SUPPORT_TASK_LIST_PATH = "/api/support_task/"
SUPPORT_TASK_DETAIL_PATH = "/api/support_task/{id}/"
SUPPORT_TASK_STATS_PATH = "/api/support_task/stats/"
SUPPORT_TASK_STAFF_USERS_PATH = "/api/support_task/staff_users/"
SUPPORT_TASK_USER_SEARCH_PATH = "/api/support_task/user_search/"

DYNAMIC_USER_LISTS_PATH = "/api/dynamic_user_lists/"
DYNAMIC_USER_LIST_DETAIL_PATH = "/api/dynamic_user_lists/{id}/"

PREMATCHING_APPOINTMENTS_LIST_PATH = "/api/matching/prematchingappointments/"

# Tool name constants — Tier A: Discovery
LIST_USER_FILTERS_REST_TOOL_NAME = "little_world_mgmt_list_user_filters"
LIST_MATCH_FILTERS_REST_TOOL_NAME = "little_world_mgmt_list_match_filters"
LIST_VIDEO_CALL_FILTERS_REST_TOOL_NAME = "little_world_mgmt_list_video_call_filters"
LIST_SCORE_FILTERS_REST_TOOL_NAME = "little_world_mgmt_list_score_filters"
LIST_DYNAMIC_USER_LISTS_REST_TOOL_NAME = "little_world_mgmt_list_dynamic_user_lists"

# Tier B: Search / list queries
QUERY_USERS_REST_TOOL_NAME = "little_world_mgmt_query_users"
QUERY_MATCHES_REST_TOOL_NAME = "little_world_mgmt_query_matches"
QUERY_VIDEO_CALLS_REST_TOOL_NAME = "little_world_mgmt_query_video_calls"
QUERY_SCORES_REST_TOOL_NAME = "little_world_mgmt_query_scores"
QUERY_SUPPORT_TASKS_REST_TOOL_NAME = "little_world_mgmt_query_support_tasks"
QUERY_PREMATCHING_APPOINTMENTS_REST_TOOL_NAME = "little_world_mgmt_query_prematching_appointments"

# Tier C: Entity detail
GET_USER_DETAIL_REST_TOOL_NAME = "little_world_mgmt_get_user_detail"
GET_MATCH_DETAIL_REST_TOOL_NAME = "little_world_mgmt_get_match_detail"
GET_VIDEO_CALL_DETAIL_REST_TOOL_NAME = "little_world_mgmt_get_video_call_detail"
GET_SCORE_DETAIL_REST_TOOL_NAME = "little_world_mgmt_get_score_detail"
GET_SUPPORT_TASK_DETAIL_REST_TOOL_NAME = "little_world_mgmt_get_support_task_detail"
GET_DYNAMIC_USER_LIST_REST_TOOL_NAME = "little_world_mgmt_get_dynamic_user_list"

# Tier D: User sub-resources
GET_USER_MESSAGES_REST_TOOL_NAME = "little_world_mgmt_get_user_messages"
GET_USER_TASKS_REST_TOOL_NAME = "little_world_mgmt_get_user_tasks"
GET_USER_NOTES_REST_TOOL_NAME = "little_world_mgmt_get_user_notes"
GET_USER_MATCH_WAITING_TIME_REST_TOOL_NAME = "little_world_mgmt_get_user_match_waiting_time"
GET_USER_PREMATCHING_APPOINTMENT_REST_TOOL_NAME = "little_world_mgmt_get_user_prematching_appointment"
GET_USER_SMS_REST_TOOL_NAME = "little_world_mgmt_get_user_sms"
GET_USER_EMAILS_REST_TOOL_NAME = "little_world_mgmt_get_user_emails"

# Tier E: Match / support auxiliaries
GET_MATCH_NOTES_REST_TOOL_NAME = "little_world_mgmt_get_match_notes"
GET_SUPPORT_TASK_STATS_REST_TOOL_NAME = "little_world_mgmt_get_support_task_stats"
SUPPORT_TASK_USER_SEARCH_REST_TOOL_NAME = "little_world_mgmt_support_task_user_search"
LIST_SUPPORT_STAFF_REST_TOOL_NAME = "little_world_mgmt_list_support_staff"

_LIST_SLUG_HINT = (
    " Prefer list=<slug> from the corresponding list_*_filters tool when the question maps to a named cohort; "
    "combine with field filters for refinement."
)


@dataclass(frozen=True)
class MgmtGetToolSpec:
    name: str
    description: str
    path: str
    paginated: bool = False


MANAGEMENT_GET_TOOL_SPECS: tuple[MgmtGetToolSpec, ...] = (
    MgmtGetToolSpec(
        LIST_USER_FILTERS_REST_TOOL_NAME,
        "List available user filter fields and saved user list slugs (all, needs_matching, journey_v2__*, :dyn:<id>, etc.).",
        USERS_FILTERS_PATH,
    ),
    MgmtGetToolSpec(
        LIST_MATCH_FILTERS_REST_TOOL_NAME,
        "List available match filter fields and saved match journey list slugs (match_journey_v2__*, etc.).",
        MATCHES_FILTERS_PATH,
    ),
    MgmtGetToolSpec(
        LIST_VIDEO_CALL_FILTERS_REST_TOOL_NAME,
        "List available video call filter fields.",
        VIDEO_CALLS_FILTERS_PATH,
    ),
    MgmtGetToolSpec(
        LIST_SCORE_FILTERS_REST_TOOL_NAME,
        "List available matching-score filter fields and reused match journey list slugs.",
        SCORES_FILTERS_PATH,
    ),
    MgmtGetToolSpec(
        LIST_DYNAMIC_USER_LISTS_REST_TOOL_NAME,
        "List saved manual dynamic user lists (id, name, description).",
        DYNAMIC_USER_LISTS_PATH,
    ),
    MgmtGetToolSpec(
        QUERY_USERS_REST_TOOL_NAME,
        "Search and list Little World users with filters, saved lists, search, and pagination." + _LIST_SLUG_HINT,
        USERS_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        QUERY_MATCHES_REST_TOOL_NAME,
        "Search and list matches with filters, saved lists, and pagination." + _LIST_SLUG_HINT,
        MATCHES_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        QUERY_VIDEO_CALLS_REST_TOOL_NAME,
        "Search and list video calls (LiveKit sessions) with participant and date filters.",
        VIDEO_CALLS_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        QUERY_SCORES_REST_TOOL_NAME,
        "Search and list two-user matching scores with score and user filters.",
        SCORES_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        QUERY_SUPPORT_TASKS_REST_TOOL_NAME,
        "List support tasks with status, priority, assignee, related user, and search filters.",
        SUPPORT_TASK_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        QUERY_PREMATCHING_APPOINTMENTS_REST_TOOL_NAME,
        "List pre-matching appointments with user and date filters.",
        PREMATCHING_APPOINTMENTS_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        GET_USER_DETAIL_REST_TOOL_NAME,
        "Retrieve full user detail by id path param (numeric id, uuid, or email).",
        USERS_DETAIL_PATH,
    ),
    MgmtGetToolSpec(
        GET_MATCH_DETAIL_REST_TOOL_NAME,
        "Retrieve match detail by id or uuid (stats, weekly activity, journey buckets).",
        MATCHES_DETAIL_PATH,
    ),
    MgmtGetToolSpec(
        GET_VIDEO_CALL_DETAIL_REST_TOOL_NAME,
        "Retrieve a single video call session by id or uuid.",
        VIDEO_CALLS_DETAIL_PATH,
    ),
    MgmtGetToolSpec(
        GET_SCORE_DETAIL_REST_TOOL_NAME,
        "Retrieve a single two-user matching score record by pk.",
        SCORES_DETAIL_PATH,
    ),
    MgmtGetToolSpec(
        GET_SUPPORT_TASK_DETAIL_REST_TOOL_NAME,
        "Retrieve a single support task by id.",
        SUPPORT_TASK_DETAIL_PATH,
    ),
    MgmtGetToolSpec(
        GET_DYNAMIC_USER_LIST_REST_TOOL_NAME,
        "Retrieve users (id, email) in a saved dynamic user list.",
        DYNAMIC_USER_LIST_DETAIL_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_MESSAGES_REST_TOOL_NAME,
        "List chat messages for a user; optional match_uuid filter; paginated.",
        USERS_MESSAGES_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        GET_USER_TASKS_REST_TOOL_NAME,
        "List open management tasks for a user.",
        USERS_TASKS_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_NOTES_REST_TOOL_NAME,
        "Retrieve internal state notes for a user.",
        USERS_NOTES_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_MATCH_WAITING_TIME_REST_TOOL_NAME,
        "Retrieve match waiting-time metrics for a user.",
        USERS_MATCH_WAITING_TIME_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_PREMATCHING_APPOINTMENT_REST_TOOL_NAME,
        "Retrieve the latest pre-matching appointment for a user.",
        USERS_PREMATCHING_APPOINTMENT_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_SMS_REST_TOOL_NAME,
        "Retrieve SMS history for a user.",
        USERS_SMS_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_EMAILS_REST_TOOL_NAME,
        "List email logs for a user; paginated.",
        USERS_EMAILS_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        GET_MATCH_NOTES_REST_TOOL_NAME,
        "Retrieve internal notes for a match.",
        MATCHES_NOTES_PATH,
    ),
    MgmtGetToolSpec(
        GET_SUPPORT_TASK_STATS_REST_TOOL_NAME,
        "Retrieve support task counts by status (NEW, IN_PROGRESS, COMPLETED).",
        SUPPORT_TASK_STATS_PATH,
    ),
    MgmtGetToolSpec(
        SUPPORT_TASK_USER_SEARCH_REST_TOOL_NAME,
        "Quick user lookup for support tasks (max 20 results); requires q query param.",
        SUPPORT_TASK_USER_SEARCH_PATH,
    ),
    MgmtGetToolSpec(
        LIST_SUPPORT_STAFF_REST_TOOL_NAME,
        "List staff users available for support task assignment.",
        SUPPORT_TASK_STAFF_USERS_PATH,
    ),
)

MANAGEMENT_REST_TOOL_NAMES: tuple[str, ...] = tuple(spec.name for spec in MANAGEMENT_GET_TOOL_SPECS)


def build_mgmt_get_rest_tool_definition(spec: MgmtGetToolSpec, api_host: str | None = None) -> RESTToolBuilder:
    resolved_api_host, hostname = resolve_api_host(api_host)
    operation_id, reduced_doc = reduce_openapi_to_endpoint(
        spectacular_schema(),
        path=spec.path,
        method="get",
        info_title=f"Little World Management {spec.name} API",
        extra_parameters=SESSION_AUTH_HEADER_PARAMS,
        servers=[{"url": resolved_api_host}],
    )
    builder = (
        RESTToolBuilder(spec.name, spec.description)
        .openapi_inline(reduced_doc)
        .operation(operation_id)
        .base_url_from_init(API_HOST_INIT_FIELD)
        .bind_session_auth()
    )
    builder = bind_openapi_call_params(builder, reduced_doc, spec.path, "get")
    builder = allow_local_tool_hosts(builder, hostname)
    if spec.paginated:
        builder = builder.timeout_seconds(30).max_response_body_bytes(512_000)
    return builder.enable()


def build_all_management_rest_tool_definitions(api_host: str | None = None) -> list[RESTToolBuilder]:
    return [build_mgmt_get_rest_tool_definition(spec, api_host=api_host) for spec in MANAGEMENT_GET_TOOL_SPECS]


def build_management_tool_init(session_init: dict[str, str]) -> dict[str, dict[str, str]]:
    return {name: dict(session_init) for name in MANAGEMENT_REST_TOOL_NAMES}
