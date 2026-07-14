from dataclasses import dataclass

from client import RESTToolBuilder, reduce_openapi_to_endpoint

from open_chat.management_tool_response_examples import (
    management_tool_response_example,
    swagger_example_is_trustworthy,
)
from open_chat.openapi_response_examples import (
    append_output_example_to_description,
    describe_openapi_response_example,
)
from open_chat.rest_tool_schema import (
    API_HOST_INIT_FIELD,
    SESSION_AUTH_HEADER_PARAMS,
    allow_local_tool_hosts,
    bind_openapi_call_params,
    patch_rest_tool_query_param_schemas,
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

_QUERY_TOOL_USAGE_HINT = (
    " Call the matching list_*_filters tool first when building non-trivial queries — it lists every filter "
    "name, valid choice values, and saved list slugs. Pass query params as scalars (strings/numbers/booleans), "
    "never JSON arrays. Omit order_by unless you need a non-default sort (pass one string such as `-date_joined`). "
    "For counts use page_size=1 and read items_total; for row data use page_size=5 by default."
)

_QUERY_USERS_USAGE_HINT = (
    _QUERY_TOOL_USAGE_HINT + " User filters include profile__user_type=learner|volunteer; state__is_onboarded, "
    "state__email_authenticated, state__user_form_completed, state__has_match_priority (true/false); "
    "profile__target_group / profile__target_groups; profile__country_of_residence; profile__job_search; "
    "state__company; joined_between_after/before; loggedin_between_after/before; search (name/email). "
    "Example onboarded learners: profile__user_type=learner&state__is_onboarded=true&page_size=1 (count)."
)

# Admin panel browser paths (React basename /matching/ — see UserPanel / UserCard in admin_panel_frontend).
# API paths use /api/matching/users/…; panel UI paths are different.
_PANEL_USER_ID = "{numeric_user_id}"
_USER_DETAIL_BASE = f"/matching/user/{_PANEL_USER_ID}"
_USER_TAB_HINT = (
    " Panel user page tabs (append ?tab=… to the user URL): "
    "profile (default), chat (support messages), emails, calls, matches, stats, notes, actions."
)
_USER_DIRECT_LINK_HINT = (
    " When staff need to open ONE user in the admin panel, always link "
    f"`{_USER_DETAIL_BASE}` using the numeric `id` field from API results — "
    "never `/matching/users/?search=…` for a known user. "
    "Example: user id 22 → `/matching/user/22`; view chat → `/matching/user/22?tab=chat`." + _USER_TAB_HINT
)
_USERS_LIST_PANEL_LINK_HINT = (
    " When sharing a filtered cohort (not a single user), link the list view with the same query params, "
    "e.g. `/matching/users/?list=all&page_size=20`. "
    "Never use page_size below 20 in panel links. "
    "Still add a direct `/matching/user/{id}` link for each specific user you discuss."
)
_MATCH_DETAIL_BASE = "/matching/match/{match_id_or_uuid}"
_MATCH_TAB_HINT = (
    f" Match page tabs: overview (default), journey, calls, notes, actions — e.g. `{_MATCH_DETAIL_BASE}?tab=notes`."
)
_MATCHES_PANEL_LINK_HINT = (
    " For a specific match, link "
    f"`{_MATCH_DETAIL_BASE}` (id or uuid from API). "
    "For filtered match lists, use `/matching/matches/?` with the same query params." + _MATCH_TAB_HINT
)
_SUPPORT_TASK_DETAIL_BASE = "/matching/support-tasks/{task_id}/"

# Structured identity fields plus profile.description (users often put their full name there).
# state.notes and dedicated notes/task tools stay uncensored — staff-only internal context.
_PROFILE_PII = ("first_name", "second_name", "phone_mobile", "description", "job_skill_description")
_STATE_PII = ("past_emails",)
_STATE_SENSITIVE = ("email_auth_pin", "email_auth_hash", "auto_login_api_token", "prematch_booking_code")

# Tools that return no end-user PII (filters, stats, metrics without identity, internal notes/tasks).
_TOOLS_WITHOUT_PII_CENSOR: frozenset[str] = frozenset(
    {
        LIST_USER_FILTERS_REST_TOOL_NAME,
        LIST_MATCH_FILTERS_REST_TOOL_NAME,
        LIST_VIDEO_CALL_FILTERS_REST_TOOL_NAME,
        LIST_SCORE_FILTERS_REST_TOOL_NAME,
        LIST_DYNAMIC_USER_LISTS_REST_TOOL_NAME,
        GET_USER_MATCH_WAITING_TIME_REST_TOOL_NAME,
        GET_USER_PREMATCHING_APPOINTMENT_REST_TOOL_NAME,
        GET_SUPPORT_TASK_STATS_REST_TOOL_NAME,
        GET_USER_NOTES_REST_TOOL_NAME,
        GET_MATCH_NOTES_REST_TOOL_NAME,
        GET_USER_TASKS_REST_TOOL_NAME,
    }
)


def _prefixed(*parts: str) -> str:
    return ".".join(part for part in parts if part)


def _profile_pii_paths(prefix: str) -> tuple[str, ...]:
    base = _prefixed(prefix)
    return tuple(_prefixed(base, f"profile.{field}") for field in _PROFILE_PII)


def _flat_profile_pii_paths(prefix: str) -> tuple[str, ...]:
    """Profile fields on objects that expose them flat (chat.partner, support profiles)."""
    base = _prefixed(prefix)
    return tuple(_prefixed(base, field) for field in _PROFILE_PII)


def _state_pii_paths(prefix: str) -> tuple[str, ...]:
    base = _prefixed(prefix)
    paths = [_prefixed(base, f"state.{field}") for field in _STATE_PII]
    paths.extend(_prefixed(base, f"state.{field}") for field in _STATE_SENSITIVE)
    return tuple(paths)


def _user_identity_paths(prefix: str = "") -> tuple[str, ...]:
    base = _prefixed(prefix)
    email = _prefixed(base, "email") if base else "email"
    return (email, *_profile_pii_paths(prefix), *_state_pii_paths(prefix))


def _match_embedded_pii_paths(prefix: str) -> tuple[str, ...]:
    base = _prefixed(prefix)
    partner = _prefixed(base, "matches.*.results.*.partner")
    chat_partner = _prefixed(base, "matches.*.results.*.chat.partner")
    paths: list[str] = []
    for field in _PROFILE_PII:
        paths.append(_prefixed(partner, field))
        paths.append(_prefixed(chat_partner, field))
    paths.append(_prefixed(base, "matches.*.results.*.chat.newest_message.text"))
    paths.append(_prefixed(base, "matches.*.results.*.report_unmatch.*.user_first_name"))
    return tuple(paths)


def _full_user_tree_paths(prefix: str = "") -> tuple[str, ...]:
    return (*_user_identity_paths(prefix), *_match_embedded_pii_paths(prefix))


def _paginated_full_user_tree_paths(prefix: str = "") -> tuple[str, ...]:
    row_prefix = _prefixed("results.*", prefix)
    return _full_user_tree_paths(row_prefix)


def _match_participant_paths(participant: str, *, paginated: bool) -> tuple[str, ...]:
    prefix = _prefixed("results.*", participant) if paginated else participant
    return (
        *_user_identity_paths(prefix),
        _prefixed(prefix, "report_unmatch.*.user_first_name"),
    )


def _video_call_participant_paths(participant: str, *, paginated: bool) -> tuple[str, ...]:
    return _match_participant_paths(participant, paginated=paginated)


def _nested_user_paths(participant: str, *, paginated: bool) -> tuple[str, ...]:
    prefix = _prefixed("results.*", participant) if paginated else participant
    return _full_user_tree_paths(prefix)


def _support_task_profile_paths(field: str, *, paginated: bool, include_email: bool) -> tuple[str, ...]:
    prefix = _prefixed("results.*", field) if paginated else field
    paths: list[str] = [
        _prefixed(prefix, "first_name"),
        _prefixed(prefix, "second_name"),
    ]
    if include_email:
        paths.insert(0, _prefixed(prefix, "email"))
    return tuple(paths)


def _support_task_paths(*, paginated: bool) -> tuple[str, ...]:
    prefix = "results.*" if paginated else ""
    base = _prefixed(prefix)
    if base:
        task_fields = (_prefixed(base, "action.parameters.message"),)
    else:
        task_fields = ("action.parameters.message",)
    return (
        *_support_task_profile_paths("related_user_profile", paginated=paginated, include_email=True),
        *_support_task_profile_paths("assigned_to_profile", paginated=paginated, include_email=False),
        *_support_task_profile_paths("created_by_profile", paginated=paginated, include_email=False),
        *task_fields,
    )


def _email_log_participant_paths(role: str) -> tuple[str, ...]:
    base = _prefixed("results.*", role)
    return (_prefixed(base, "email"), *_profile_pii_paths(base))


def _user_messages_paths() -> tuple[str, ...]:
    return (
        *_flat_profile_pii_paths("chat.partner"),
        "chat.newest_message.text",
        "messages.results.*.text",
    )


def _top_level_array_identity_paths(*, include_last_name: bool = False) -> tuple[str, ...]:
    paths = ("*.email", "*.first_name", "*.second_name")
    if include_last_name:
        return (*paths, "*.last_name")
    return paths


@dataclass(frozen=True)
class MgmtGetToolSpec:
    name: str
    description: str
    path: str
    paginated: bool = False


MANAGEMENT_GET_TOOL_SPECS: tuple[MgmtGetToolSpec, ...] = (
    MgmtGetToolSpec(
        LIST_USER_FILTERS_REST_TOOL_NAME,
        "List available user filter fields, valid choice values, and saved user list slugs "
        "(all, needs_matching, journey_v2__*, :dyn:<id>, etc.). "
        "Call this before query_users when filters or list slugs are unclear. "
        "Interests/hobbies are not filterable here — they appear only in query_users rows and get_user_detail.",
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
        "Search and list Little World users with filters, saved lists, search, and pagination."
        " Each result includes profile.interests; interests/hobbies cannot be filtered server-side — "
        "paginate with page_size=5 and inspect rows, or call get_user_detail for one user."
        + _QUERY_USERS_USAGE_HINT
        + _LIST_SLUG_HINT
        + _USERS_LIST_PANEL_LINK_HINT
        + _USER_DIRECT_LINK_HINT,
        USERS_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        QUERY_MATCHES_REST_TOOL_NAME,
        "Search and list matches with filters, saved lists, and pagination."
        + _QUERY_TOOL_USAGE_HINT
        + _LIST_SLUG_HINT
        + _MATCHES_PANEL_LINK_HINT,
        MATCHES_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        QUERY_VIDEO_CALLS_REST_TOOL_NAME,
        "Search and list video calls (LiveKit sessions) with participant and date filters."
        + _QUERY_TOOL_USAGE_HINT
        + " Participant user pages: `/matching/user/{participant_numeric_id}`.",
        VIDEO_CALLS_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        QUERY_SCORES_REST_TOOL_NAME,
        "Search and list two-user matching scores with score and user filters." + _QUERY_TOOL_USAGE_HINT,
        SCORES_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        QUERY_SUPPORT_TASKS_REST_TOOL_NAME,
        "List support tasks with status, priority, assignee, related user, and search filters."
        + _QUERY_TOOL_USAGE_HINT
        + f" Task detail panel: `{_SUPPORT_TASK_DETAIL_BASE}`; related user: `/matching/user/{{related_user_id}}`.",
        SUPPORT_TASK_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        QUERY_PREMATCHING_APPOINTMENTS_REST_TOOL_NAME,
        "List pre-matching appointments with user and date filters."
        + _QUERY_TOOL_USAGE_HINT
        + " Each row includes nested user — link `/matching/user/{user.id}` for that learner/volunteer.",
        PREMATCHING_APPOINTMENTS_LIST_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        GET_USER_DETAIL_REST_TOOL_NAME,
        "Retrieve one user's full profile and state by path param `id` (numeric user id, uuid, or email). "
        "Use for a named/known user or fields not exposed as list filters (interests, description, match buckets). "
        "After query_users, pass id/uuid/email from a result row."
        + _USER_DIRECT_LINK_HINT
        + " Panel profile tab shows onboarding status, interests, languages, and match icons.",
        USERS_DETAIL_PATH,
    ),
    MgmtGetToolSpec(
        GET_MATCH_DETAIL_REST_TOOL_NAME,
        "Retrieve one match's full detail by path param `id` (numeric match id or uuid): participants, stats, "
        "weekly activity, journey buckets. Use after query_matches when staff ask about a specific match."
        + _MATCHES_PANEL_LINK_HINT,
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
        f"Retrieve a single support task by id. Panel: `{_SUPPORT_TASK_DETAIL_BASE}`.",
        SUPPORT_TASK_DETAIL_PATH,
    ),
    MgmtGetToolSpec(
        GET_DYNAMIC_USER_LIST_REST_TOOL_NAME,
        "Retrieve users (id, email) in a saved dynamic user list.",
        DYNAMIC_USER_LIST_DETAIL_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_MESSAGES_REST_TOOL_NAME,
        "List chat messages for a user; optional match_uuid filter; paginated."
        " For staff who want to read or reply in the panel, link `/matching/user/{id}?tab=chat` "
        "(same numeric id as the path param).",
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
        "Retrieve internal state notes for a user. Panel notes editor: `/matching/user/{id}?tab=notes`.",
        USERS_NOTES_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_MATCH_WAITING_TIME_REST_TOOL_NAME,
        "Retrieve match waiting-time metrics for a user (also shown on the profile tab).",
        USERS_MATCH_WAITING_TIME_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_PREMATCHING_APPOINTMENT_REST_TOOL_NAME,
        "Retrieve the latest pre-matching appointment for a user.",
        USERS_PREMATCHING_APPOINTMENT_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_SMS_REST_TOOL_NAME,
        "Retrieve SMS history for a user."
        " Sending SMS is done from panel Actions tab: `/matching/user/{id}?tab=actions`.",
        USERS_SMS_PATH,
    ),
    MgmtGetToolSpec(
        GET_USER_EMAILS_REST_TOOL_NAME,
        "List email logs for a user; paginated. Panel email log UI: `/matching/user/{id}?tab=emails`.",
        USERS_EMAILS_PATH,
        paginated=True,
    ),
    MgmtGetToolSpec(
        GET_MATCH_NOTES_REST_TOOL_NAME,
        f"Retrieve internal notes for a match. Panel: `{_MATCH_DETAIL_BASE}?tab=notes`.",
        MATCHES_NOTES_PATH,
    ),
    MgmtGetToolSpec(
        GET_SUPPORT_TASK_STATS_REST_TOOL_NAME,
        "Retrieve support task counts by status (NEW, IN_PROGRESS, COMPLETED).",
        SUPPORT_TASK_STATS_PATH,
    ),
    MgmtGetToolSpec(
        SUPPORT_TASK_USER_SEARCH_REST_TOOL_NAME,
        "Quick user lookup for support tasks (max 20 results); requires q query param." + _USER_DIRECT_LINK_HINT,
        SUPPORT_TASK_USER_SEARCH_PATH,
    ),
    MgmtGetToolSpec(
        LIST_SUPPORT_STAFF_REST_TOOL_NAME,
        "List staff users available for support task assignment.",
        SUPPORT_TASK_STAFF_USERS_PATH,
    ),
)

MANAGEMENT_REST_TOOL_NAMES: tuple[str, ...] = tuple(spec.name for spec in MANAGEMENT_GET_TOOL_SPECS)


def _censor_paths_for_spec(spec: MgmtGetToolSpec) -> tuple[str, ...]:
    name = spec.name
    if name == QUERY_USERS_REST_TOOL_NAME:
        return _paginated_full_user_tree_paths()
    if name == GET_USER_DETAIL_REST_TOOL_NAME:
        return _full_user_tree_paths()
    if name == QUERY_MATCHES_REST_TOOL_NAME:
        return (
            *_match_participant_paths("user1", paginated=True),
            *_match_participant_paths("user2", paginated=True),
        )
    if name == GET_MATCH_DETAIL_REST_TOOL_NAME:
        return (
            *_match_participant_paths("user1", paginated=False),
            *_match_participant_paths("user2", paginated=False),
        )
    if name == QUERY_VIDEO_CALLS_REST_TOOL_NAME:
        return (
            *_video_call_participant_paths("u1", paginated=True),
            *_video_call_participant_paths("u2", paginated=True),
        )
    if name == GET_VIDEO_CALL_DETAIL_REST_TOOL_NAME:
        return (
            *_video_call_participant_paths("u1", paginated=False),
            *_video_call_participant_paths("u2", paginated=False),
        )
    if name == QUERY_SCORES_REST_TOOL_NAME:
        return (
            *_nested_user_paths("user1", paginated=True),
            *_nested_user_paths("user2", paginated=True),
        )
    if name == GET_SCORE_DETAIL_REST_TOOL_NAME:
        return (
            *_nested_user_paths("user1", paginated=False),
            *_nested_user_paths("user2", paginated=False),
        )
    if name in {QUERY_SUPPORT_TASKS_REST_TOOL_NAME, GET_SUPPORT_TASK_DETAIL_REST_TOOL_NAME}:
        return _support_task_paths(paginated=name == QUERY_SUPPORT_TASKS_REST_TOOL_NAME)
    if name == QUERY_PREMATCHING_APPOINTMENTS_REST_TOOL_NAME:
        return _nested_user_paths("user", paginated=True)
    if name == GET_DYNAMIC_USER_LIST_REST_TOOL_NAME:
        return ("*.email",)
    if name == GET_USER_MESSAGES_REST_TOOL_NAME:
        return _user_messages_paths()
    if name == GET_USER_EMAILS_REST_TOOL_NAME:
        return (
            *_email_log_participant_paths("sender"),
            *_email_log_participant_paths("receiver"),
            "results.*.data",
        )
    if name == GET_USER_SMS_REST_TOOL_NAME:
        return ("*.message",)
    if name == SUPPORT_TASK_USER_SEARCH_REST_TOOL_NAME:
        return _top_level_array_identity_paths()
    if name == LIST_SUPPORT_STAFF_REST_TOOL_NAME:
        return _top_level_array_identity_paths(include_last_name=True)
    return ()


def build_mgmt_get_rest_tool_definition(spec: MgmtGetToolSpec, api_host: str | None = None) -> RESTToolBuilder:
    resolved_api_host, hostname = resolve_api_host(api_host)
    schema = spectacular_schema()
    description = append_output_example_to_description(
        spec.description,
        describe_openapi_response_example(
            schema,
            path=spec.path,
            method="get",
            fallback=management_tool_response_example(spec.path),
            trust_example=swagger_example_is_trustworthy,
        ),
    )
    operation_id, reduced_doc = reduce_openapi_to_endpoint(
        schema,
        path=spec.path,
        method="get",
        info_title=f"Little World Management {spec.name} API",
        extra_parameters=SESSION_AUTH_HEADER_PARAMS,
        servers=[{"url": resolved_api_host}],
    )
    reduced_doc = patch_rest_tool_query_param_schemas(reduced_doc, spec.path, method="get")
    builder = (
        RESTToolBuilder(spec.name, description)
        .openapi_inline(reduced_doc)
        .operation(operation_id)
        .base_url_from_init(API_HOST_INIT_FIELD)
        .bind_session_auth()
    )
    builder = bind_openapi_call_params(builder, reduced_doc, spec.path, "get")
    builder = allow_local_tool_hosts(builder, hostname)
    if spec.paginated:
        builder = builder.timeout_seconds(30).max_response_body_bytes(512_000)
    censor_paths = _censor_paths_for_spec(spec)
    if censor_paths:
        builder = builder.censor_response_paths(*censor_paths)
    return builder.enable()


def build_all_management_rest_tool_definitions(api_host: str | None = None) -> list[RESTToolBuilder]:
    return [build_mgmt_get_rest_tool_definition(spec, api_host=api_host) for spec in MANAGEMENT_GET_TOOL_SPECS]


def build_management_tool_init(session_init: dict[str, str]) -> dict[str, dict[str, str]]:
    return {name: dict(session_init) for name in MANAGEMENT_REST_TOOL_NAMES}
