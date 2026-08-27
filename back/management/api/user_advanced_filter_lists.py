import inspect
from dataclasses import dataclass

from management.api.user_advanced_filter import (
    EXTRA__fh_aachen_learners_scoring,
    EXTRA__fh_aachen_users,
    EXTRA__learners_with_activity_in_last3weeks,
    EXTRA__lingoda_learners_scoring,
    EXTRA__lingoda_users,
    EXTRA__onboarded_volunteers_with_activity_in_last3weeks,
    EXTRA__refugee_learners_scoring,
    EXTRA__suggestion_match_completed_off_plattform,
    EXTRA__suggestion_match_completed_on_plattform,
    all_users,
    eligible_for_random_calls,
    get_active_match_query_set,
    get_quality_match_query_set,
    get_user_with_message_to_admin,
    get_user_with_message_to_admin_that_are_read_but_not_replied,
    get_user_with_message_to_admin_that_are_read_or_not_read_but_not_replied,
    get_users_with_company,
    get_volunteers_booked_onboarding_call_but_never_visited,
    logged_in_within_3weeks,
    needs_matching,
    needs_matching_volunteers,
    only_hd_test_user,
    searching_users,
    users_in_registration,
    users_require_prematching_call_not_booked,
    users_with_booked_prematching_call,
    users_with_open_proposals,
    users_with_open_tasks,
)
from management.api.user_journey_filters import (
    EXTRA__random_call_email_blast_2026_08_27,
    active_match,
    all_volunteers_min_one_no_ongoing_match,
    booked_onboarding_call,
    community__active_volunteers,
    community__ehrenamtliche_und_lernende_with_a1a2,
    community__learners_better_than_a1a2,
    community_calls,
    completed_form__created_within_6months,
    completed_form__created_within_6months_no_onboarding_call,
    completed_form__created_within_6months_no_onboarding_call_volunteer,
    completed_form__no__onboarding_call,
    email_not_verified_or_form_not_completed,
    email_verified,
    email_verified_and_form_completed,
    failed_matching,
    first_search_learners,
    first_search_v1,
    first_search_v2,
    first_search_volunteers,
    gave_up_searching,
    happy_active,
    happy_inactive,
    learners_better_than_a1a2,
    learners_with_a1a2,
    marked_unresponsive,
    match_takeoff,
    never_active,
    never_active_or_deleted,
    never_active_or_deleted_or_created,
    no_confirm,
    no_show,
    not_too_low_german_level__is_onboarded,
    onboarding_incomplete,
    ongoing_non_completed_match,
    over_30_days_after_prematching_still_searching,
    pre_matching,
    self_onboarding_started_no_booked_call,
    subscribed_to_newsletter,
    too_low_german_level,
    too_low_german_level_or_not_onboarded,
    user_created,
    user_deleted,
    user_form_completed,
    user_searching,
    users_with_duplicate_automatic_emails_29_01_2026,
    volunteers_with_completed_match_no_ongoing,
)
from management.models.dynamic_user_list import DynamicUserList

GITHUB_SOURCE_ROOT = "https://github.com/a-little-world/little-world-core/blob/main"


def _catalog_queryset(list_id: str):
    """Serve a list straight from the analytics catalog entry that defines it.

    The catalog is the only place an analytics query is named. Entries built this way
    therefore cannot disagree with it — which is what
    ``registry.catalog_keys_disagreeing_with_filter_lists`` had to police back when the
    filter list named the query a second time.

    Resolution is deferred to call time to avoid a circular import: the analytics
    catalog imports query functions from this module's neighbours.
    """

    def fn(qs=None):
        from management.analytics.registry import get_catalog_entry
        from management.models.user import User

        return get_catalog_entry(list_id).queryset(User.objects.all() if qs is None else qs)

    fn.__name__ = list_id
    fn.__qualname__ = list_id
    fn._catalog_list_id = list_id
    return fn


def _unwrap_analytics_queryset(queryset: callable) -> callable:
    """Resolve a catalog wrapper to the query function it ultimately calls.

    Keeps the admin "view source" link pointing at the query definition
    (``queries/funnel.py``, ``queries/state.py``) rather than at the wrapper.
    """
    list_id = getattr(queryset, "_catalog_list_id", None)
    if list_id is None:
        return queryset

    from management.analytics.registry import get_catalog_entry

    entry = get_catalog_entry(list_id)
    return entry.queryset if entry else queryset


def get_queryset_source_reference(queryset: callable) -> dict:
    if queryset is None:
        return {"source_file": None, "source_line": None, "source_url": None}

    queryset = _unwrap_analytics_queryset(queryset)

    try:
        source_line = inspect.getsourcelines(queryset)[1]
    except (OSError, TypeError):
        source_line = None

    module_name = getattr(queryset, "__module__", "")
    source_file = f"back/{module_name.replace('.', '/')}.py" if module_name else None
    source_url = None
    if source_file and source_line:
        source_url = f"{GITHUB_SOURCE_ROOT}/{source_file}#L{source_line}"

    return {"source_file": source_file, "source_line": source_line, "source_url": source_url}


def _catalog_entry(list_id: str):
    """Lazy catalog lookup — this module and the analytics registry import each other."""
    from management.analytics.registry import get_catalog_entry

    return get_catalog_entry(list_id)


def _catalog_description(list_id: str) -> str | None:
    """Description from the analytics catalog, which owns it for every ID it defines."""
    entry = _catalog_entry(list_id)
    return entry.description if entry else None


_COMMUNICATIONS_LIST_IDS = frozenset(
    {
        "message_reply_required",
        "read_message_but_not_replied",
        "read_or_not_read_but_not_replied",
        "newsletter_subscribed",
        "EXTRA__users_with_duplicate_automatic_emails_29_01_2026",
    }
)

_JOURNEY_V4_PREFIX = "journey_v2__"
_MATCH_JOURNEY_V4_PREFIX = "match_journey_v2__"


def category_for_list_id(name: str) -> str:
    """High-level group shown in the admin list picker so neighbouring IDs stay distinct."""
    if name.startswith(":dyn:"):
        return "Dynamic"
    if name.startswith(("state__", "funnel__")):
        return "User Journey"
    if name.startswith(_JOURNEY_V4_PREFIX):
        return "User Journey V4"
    if name.startswith(("match_state__", "match_funnel__")):
        return "Match Journey"
    if name.startswith(_MATCH_JOURNEY_V4_PREFIX):
        return "Match Journey V4"
    if name.startswith("community"):
        return "Community"
    if name in _COMMUNICATIONS_LIST_IDS:
        return "Communications"
    if name.startswith(("EXTRA__", "TEST__")):
        return "Extra"
    return "Operations"


def _humanize_list_name(name: str) -> str:
    slug = name.rsplit("__", 1)[-1]
    return slug.replace("_", " ").strip()


def _first_doc_line(queryset) -> str | None:
    if queryset and queryset.__doc__:
        return queryset.__doc__.strip().split("\n", 1)[0].strip()
    return None


@dataclass
class FilterListEntry:
    name: str
    description: str | None
    queryset: callable = None
    #: Picker group for entries whose ``name`` carries no recognisable prefix. Synthetic
    #: lists built at request time (appointment slots) would otherwise fall through
    #: ``category_for_list_id`` to the catch-all group.
    category_override: str | None = None

    def resolved_description(self) -> str | None:
        """Catalog first (conventions §4), then the hardcoded value, then the docstring.

        The catalog wins so a description added here cannot silently diverge from the
        canonical one; ``assert_all_domains_strict`` rejects hardcoding both.
        """
        catalog_description = _catalog_description(self.name)
        if catalog_description is not None:
            return catalog_description
        if self.description is not None:
            return self.description
        if self.queryset and self.queryset.__doc__:
            return self.queryset.__doc__.strip()
        return None

    def resolved_display_name(self) -> str:
        """Short title for pickers. Catalog ``display_name`` wins; description stays the long copy."""
        entry = _catalog_entry(self.name)
        if entry is not None:
            return entry.display_name
        if self.description:
            return self.description.strip()
        return _first_doc_line(self.queryset) or _humanize_list_name(self.name)

    def category(self) -> str:
        return self.category_override or category_for_list_id(self.name)

    def picker_label(self) -> str:
        display_name = self.resolved_display_name()
        category = self.category()
        if display_name.startswith(f"{category} - "):
            return display_name
        return f"{category} - {display_name}"

    def to_dict(self):
        source_reference = get_queryset_source_reference(self.queryset)
        return {
            "name": self.name,
            "description": self.resolved_description(),
            "display_name": self.resolved_display_name(),
            "category": self.category(),
            "label": self.picker_label(),
            **source_reference,
        }


PANEL_V1_FILTER_LISTS = [
    FilterListEntry("all", None, all_users),
    FilterListEntry("searching", None, searching_users),
    FilterListEntry("needs_matching", None, needs_matching),
    FilterListEntry("in_registration", None, users_in_registration),
    FilterListEntry("active_match", None, get_active_match_query_set),
    FilterListEntry("logged_in_within_3weeks", None, logged_in_within_3weeks),
    FilterListEntry("highquality_matching", None, get_quality_match_query_set),
    FilterListEntry("message_reply_required", None, get_user_with_message_to_admin),
    FilterListEntry("read_message_but_not_replied", None, get_user_with_message_to_admin_that_are_read_but_not_replied),
    FilterListEntry(
        "read_or_not_read_but_not_replied",
        None,
        get_user_with_message_to_admin_that_are_read_or_not_read_but_not_replied,
    ),
    FilterListEntry("users_with_company", None, get_users_with_company),
    FilterListEntry("users_with_open_tasks", None, users_with_open_tasks),
    FilterListEntry("users_with_open_proposals", None, users_with_open_proposals),
    FilterListEntry(
        "volunteers_booked_onboarding_call_but_never_visited",
        None,
        get_volunteers_booked_onboarding_call_but_never_visited,
    ),
    FilterListEntry("users_require_prematching_call_not_booked", None, users_require_prematching_call_not_booked),
    FilterListEntry("users_with_booked_prematching_call", None, users_with_booked_prematching_call),
    FilterListEntry("users_with_booked_prematching_call_exclude_had", None, users_with_booked_prematching_call),
]

CORE_LISTS = [
    "journey_v2__user_created",
    "journey_v2__email_verified",
    "journey_v2__user_form_completed",
    "journey_v2__booked_onboarding_call",
    "journey_v2__self_onboarding_started",
    "journey_v2__first_search",
    "journey_v2__user_searching_again",
    "journey_v2__pre_matching",
    "journey_v2__match_takeoff",
    "journey_v2__active_matching",
    "journey_v2__never_active",
    "journey_v2__no_show",
    "journey_v2__no_confirm",
    "journey_v2__happy_inactive",
    "journey_v2__too_low_german_level",
    "journey_v2__unmatched",
    "journey_v2__gave_up_searching",
    "journey_v2__user_deleted",
]

MAIN_USER_JOURNEY = [
    "journey_v2__user_created",
    "journey_v2__never_active_or_deleted",
    "journey_v2__email_verified",
    "journey_v2__user_form_completed",
    "journey_v2__booked_onboarding_call",
    "journey_v2__self_onboarding_started",
    "journey_v2__first_search",
    "journey_v2__first_search_v2",
    "journey_v2__first_search_volunteers",
    "journey_v2__first_search_learners",
    "journey_v2__user_searching_again",
    "journey_v2__pre_matching",
    "journey_v2__match_takeoff",
    "journey_v2__active_matching",
    # "journey_v2__ongoing_non_completed_match",
    "journey_v2__never_active",
    "journey_v2__no_show",
    "journey_v2__no_confirm",
    "journey_v2__failed_matching",
    "journey_v2__happy_inactive",
    "journey_v2__happy_active",
    "journey_v2__too_low_german_level",
    "journey_v2__unmatched",
    "journey_v2__gave_up_searching",
    "journey_v2__user_deleted",
    "journey_v2__marked_unresponsive",
    "journey_v2__never_active_or_deleted_or_created",
    "journey_v2__email_verified_and_form_completed",
    "journey_v2__email_not_verified_or_form_not_completed",
]

USER_JOURNEY_FILTER_LISTS = [
    FilterListEntry("journey_v2__user_created", None, user_created),
    FilterListEntry("journey_v2__never_active_or_deleted", None, never_active_or_deleted),
    FilterListEntry("journey_v2__email_verified", None, email_verified),
    FilterListEntry("journey_v2__user_form_completed", None, user_form_completed),
    FilterListEntry("journey_v2__booked_onboarding_call", None, booked_onboarding_call),
    FilterListEntry("journey_v2__self_onboarding_started", None, self_onboarding_started_no_booked_call),
    FilterListEntry("journey_v2__onboarding_incomplete", None, onboarding_incomplete),
    FilterListEntry("journey_v2__first_search", None, first_search_v1),
    FilterListEntry("journey_v2__first_search_v2", None, first_search_v2),
    FilterListEntry("journey_v2__first_search_volunteers", None, first_search_volunteers),
    FilterListEntry("journey_v2__first_search_learners", None, first_search_learners),
    FilterListEntry("journey_v2__user_searching_again", None, user_searching),
    FilterListEntry("journey_v2__pre_matching", None, pre_matching),
    FilterListEntry("journey_v2__match_takeoff", None, match_takeoff),
    FilterListEntry("journey_v2__active_matching", None, active_match),
    FilterListEntry("journey_v2__ongoing_non_completed_match", None, ongoing_non_completed_match),
    FilterListEntry("journey_v2__never_active", None, never_active),
    FilterListEntry("journey_v2__no_show", None, no_show),
    # FilterListEntry("journey_v2__user_ghosted", None, ghoster), Was depricated!
    FilterListEntry("journey_v2__no_confirm", None, no_confirm),
    FilterListEntry("journey_v2__failed_matching", None, failed_matching),
    FilterListEntry("journey_v2__happy_inactive", None, happy_inactive),
    FilterListEntry("journey_v2__happy_active", None, happy_active),
    FilterListEntry("journey_v2__too_low_german_level", None, too_low_german_level),
    FilterListEntry("journey_v2__unmatched", None, over_30_days_after_prematching_still_searching),
    FilterListEntry("journey_v2__gave_up_searching", None, gave_up_searching),
    FilterListEntry("journey_v2__user_deleted", None, user_deleted),
    FilterListEntry("journey_v2__marked_unresponsive", None, marked_unresponsive),
    FilterListEntry("journey_v2__never_active_or_deleted_or_created", None, never_active_or_deleted_or_created),
    FilterListEntry("journey_v2__email_verified_and_form_completed", None, email_verified_and_form_completed),
    FilterListEntry(
        "journey_v2__email_not_verified_or_form_not_completed", None, email_not_verified_or_form_not_completed
    ),
    FilterListEntry("journey_v2__not_too_low_german_level__is_onboarded", None, not_too_low_german_level__is_onboarded),
    FilterListEntry("journey_v2__too_low_german_level_or_not_onboarded", None, too_low_german_level_or_not_onboarded),
    FilterListEntry("needs_matching_volunteers", None, needs_matching_volunteers),
    FilterListEntry("herrduenschnlate", None, only_hd_test_user),
    FilterListEntry("community", None, community_calls),
    FilterListEntry("community__active_volunteers", None, community__active_volunteers),
    FilterListEntry("learners_with_a1a2", "Learners with A1/A2", learners_with_a1a2),
    FilterListEntry("learners_better_than_a1a2", "Learners with at least B1", learners_better_than_a1a2),
    FilterListEntry(
        "community__learners_better_than_a1a2",
        "Commmunity and Learners with at least B1",
        community__learners_better_than_a1a2,
    ),
    FilterListEntry(
        "community__6weeks__ehrenamtliche_und_lernende_with_a1a2",
        "(Community) Last 6 Weeks & Ehrenamtliche und Lernende with A1A2",
        community__ehrenamtliche_und_lernende_with_a1a2,
    ),
    # FilterListEntry("community__ehrenamtliche_und_lernende_with_a1a2", "Community-Call & Ehrenamtliche und Lernende with A1A2", community__ehrenamtliche_und_lernende_with_a1a2),
    FilterListEntry("newsletter_subscribed", None, subscribed_to_newsletter),
    FilterListEntry("completed_form__no__onboarding_call", None, completed_form__no__onboarding_call),
    FilterListEntry("completed_form__created_within_6months", None, completed_form__created_within_6months),
    FilterListEntry(
        "completed_form__created_within_6months_no_onboarding_call",
        None,
        completed_form__created_within_6months_no_onboarding_call,
    ),
    FilterListEntry(
        "completed_form__created_within_6months_no_onboarding_call_volunteer",
        None,
        completed_form__created_within_6months_no_onboarding_call_volunteer,
    ),
    FilterListEntry("TEST__all_volunteers_min_one_no_ongoing_match", None, all_volunteers_min_one_no_ongoing_match),
    FilterListEntry(
        "EXTRA__volunteers_with_completed_match_no_ongoing",
        "Volunteers with at least one completed match and no ongoing matches",
        volunteers_with_completed_match_no_ongoing,
    ),
    FilterListEntry(
        "EXTRA__users_with_duplicate_automatic_emails_29_01_2026",
        "Users who received multiple emails (u023/u024/u025) on 29.01.2026",
        users_with_duplicate_automatic_emails_29_01_2026,
    ),
    FilterListEntry("EXTRA__lingoda_users", "Lingoda users", EXTRA__lingoda_users),
    FilterListEntry(
        "EXTRA__random_call_email_blast_2026_08_27",
        "Random Call e-mail blast 27 Aug 2026 (apology audience)",
        EXTRA__random_call_email_blast_2026_08_27,
    ),
    FilterListEntry("EXTRA__lingoda_learners_scoring", "Lingoda learners for scoring", EXTRA__lingoda_learners_scoring),
    FilterListEntry("EXTRA__fh_aachen_users", "FH Aachen users", EXTRA__fh_aachen_users),
    FilterListEntry(
        "EXTRA__fh_aachen_learners_scoring", "FH Aachen learners for scoring", EXTRA__fh_aachen_learners_scoring
    ),
    FilterListEntry("EXTRA__refugee_learners_scoring", "Refugee learners for scoring", EXTRA__refugee_learners_scoring),
    FilterListEntry(
        "EXTRA__learners_with_activity_in_last3weeks",
        "Learners with activity in the last 3 weeks",
        EXTRA__learners_with_activity_in_last3weeks,
    ),
    FilterListEntry(
        "EXTRA__onboarded_volunteers_with_activity_in_last3weeks",
        "Onboarded Volunteers with activity in the last 3 weeks",
        EXTRA__onboarded_volunteers_with_activity_in_last3weeks,
    ),
    FilterListEntry(
        "EXTRA__eligible_for_random_calls",
        "Users eligible for random calls onboarding+German criteria",
        eligible_for_random_calls,
    ),
    FilterListEntry(
        "EXTRA__suggestion_match_completed_on_plattform",
        "Users with a match that reached 8 on-platform video-call units",
        EXTRA__suggestion_match_completed_on_plattform,
    ),
    FilterListEntry(
        "EXTRA__suggestion_match_completed_off_plattform",
        "Users with a match marked as completed off platform",
        EXTRA__suggestion_match_completed_off_plattform,
    ),
]

# Servable IDs from ``management.analytics.user_journey.catalog``, split by construct.
#
# Listed rather than derived: importing the catalog here is circular, because the
# analytics queries still import legacy filters out of ``management.api`` and that
# package's ``__init__`` pulls this module back in. (Untangling that layering — analytics
# should not depend on the API layer at all — is worth doing, but not in this change.)
#
# Only the IDs are repeated, never the queries: ``_catalog_queryset`` resolves each one
# through the catalog at call time, and ``registry.catalog_keys_not_servable`` fails the
# registry test the moment a catalog key is missing from these tuples.
#
# Descriptions stay ``None`` — the catalog owns display_name/description (conventions §4)
# and ``resolved_description`` reads it from there.
#
# V4 ``journey_v2__*`` lists stay in ``USER_JOURNEY_FILTER_LISTS`` above, untouched.

FUNNEL_LIST_IDS = (
    "funnel__all",
    "funnel__active_adjusted",
    "funnel__email_verified",
    "funnel__form_completed",
    "funnel__eligible_for_onboarding",
    "funnel__onboarding_started",
    "funnel__onboarded",
    "funnel__ineligible_a0_german",
    "funnel__ineligible_outside_germany",
    "funnel__ineligible_for_onboarding",
    "funnel__form_completed_awaiting_onboarding",
)

# V5 partition cells + composites/drill-downs that are not cells.
STATE_LIST_IDS = (
    "state__email_unverified",
    "state__form_unfilled",
    "state__onboarding_not_started",
    "state__onboarding_booked",
    "state__self_onboarding",
    "state__onboarding_no_show",
    "state__onboarding_ineligible",
    "state__gave_up",
    "state__first_search",
    "state__first_search_no_proposal",
    "state__first_search_proposal_expired",
    "state__first_search_rejected_by_them",
    "state__first_search_rejected_by_partner",
    "state__first_search_proposal_closed",
    "state__search_blocked",
    "state__proposed",
    "state__first_match_kickoff",
    "state__first_match_ongoing",
    "state__rematch_proposed",
    "state__searching_after_failed",
    "state__stopped_after_failed",
    "state__success_ongoing_searching",
    "state__success_ongoing_settled",
    "state__success_searching",
    "state__success_idle",
    "state__unresponsive_after_success",
    "state__unresponsive",
    "state__deleted_after_success",
    "state__deleted",
    "state__record_incomplete",
    "state__failed_match_reasons",
)

ANALYTICS_FILTER_LISTS = [
    FilterListEntry(list_id, None, _catalog_queryset(list_id)) for list_id in (*FUNNEL_LIST_IDS, *STATE_LIST_IDS)
]

FILTER_LISTS = (
    PANEL_V1_FILTER_LISTS
    + ANALYTICS_FILTER_LISTS
    + [entry for entry in USER_JOURNEY_FILTER_LISTS if not entry.name.startswith(_JOURNEY_V4_PREFIX)]
    + [entry for entry in USER_JOURNEY_FILTER_LISTS if entry.name.startswith(_JOURNEY_V4_PREFIX)]
)


def get_dynamic_userlists() -> list[FilterListEntry]:
    return [
        FilterListEntry(":dyn:" + str(dyn_user_list.id), dyn_user_list.name)
        for dyn_user_list in DynamicUserList.objects.all()
    ]


def get_choices():
    try:
        return [(entry.name, entry.picker_label()) for entry in FILTER_LISTS + get_dynamic_userlists()]
    except Exception as e:
        print(e)
        return []


def get_list_by_name(name):
    for element in FILTER_LISTS + get_dynamic_userlists():
        if element.name == name:
            return element
    return None
