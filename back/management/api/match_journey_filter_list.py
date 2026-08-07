from management.api.match_journey_filters import (
    EXTRA__suggestion_match_completed_off_plattform,
    EXTRA__suggestion_match_completed_on_plattform,
    all_matches,
    completed_match,
    contact_stopped,
    expired_matching_proposals,
    failed_matches,
    match_completed_off_plattform,
    match_confirmed_no_contact,
    match_confirmed_single_party_contact,
    match_first_contact,
    match_free_play,
    match_one_user_viewed,
    match_ongoing,
    match_unviewed,
    matching_proposals,
    never_confirmed,
    no_contact,
    ongoing_matches,
    only_non_support_matching,
    organic_match,
    reported_or_removed_match,
    sucess_matches,
    support_matching,
    user_ghosted,
)
from management.api.user_advanced_filter_lists import FilterListEntry, get_queryset_source_reference  # noqa: F401
from management.models.matches import Match
from management.models.unconfirmed_matches import MatchType

# One definition of a filter list entry, shared with the user lists — promoted here on
# the second caller rather than kept as a near-identical copy (conventions §1).
MATCH_JOURNEY_FILTERS = [
    FilterListEntry("match_journey_v2__all", None, all_matches),
    FilterListEntry(
        "match_journey_v2__only_non_support_matching",
        None,
        only_non_support_matching,
    ),
    FilterListEntry(
        "match_journey_v2__organic_match",
        "Random call matches",
        organic_match,
    ),
    FilterListEntry(
        "match_journey_v2__proposed_matches",
        None,
        matching_proposals,
    ),
    FilterListEntry(
        "match_journey_v2__unviewed",
        None,
        match_unviewed,
    ),
    FilterListEntry(
        "match_journey_v2__one_user_viewed",
        None,
        match_one_user_viewed,
    ),
    FilterListEntry(
        "match_journey_v2__confirmed_no_contact",
        None,
        match_confirmed_no_contact,
    ),
    FilterListEntry(
        "match_journey_v2__confirmed_single_party_contact",
        None,
        match_confirmed_single_party_contact,
    ),
    FilterListEntry(
        "match_journey_v2__first_contact",
        None,
        match_first_contact,
    ),
    FilterListEntry(
        "match_journey_v2__match_ongoing",
        None,
        match_ongoing,
    ),
    FilterListEntry(
        "match_journey_v2__match_free_play",
        None,
        match_free_play,
    ),
    FilterListEntry(
        "match_journey_v2__completed_match",
        None,
        completed_match,
    ),
    FilterListEntry(
        "match_journey_v2__never_confirmed",
        None,
        never_confirmed,
    ),
    FilterListEntry(
        "match_journey_v2__no_contact",
        None,
        no_contact,
    ),
    FilterListEntry(
        "match_journey_v2__user_ghosted",
        None,
        user_ghosted,
    ),
    FilterListEntry(
        "match_journey_v2__contact_stopped",
        None,
        contact_stopped,
    ),
    FilterListEntry(
        "match_journey_v2__expired_proposals",
        None,
        expired_matching_proposals,
    ),
    FilterListEntry(
        "match_journey_v2__reported_or_removed",
        None,
        reported_or_removed_match,
    ),
    FilterListEntry(
        "match_journey_v2__sucess_matches",
        None,
        sucess_matches,
    ),
    FilterListEntry(
        "match_journey_v2__ongoing_matches",
        None,
        ongoing_matches,
    ),
    FilterListEntry(
        "match_journey_v2__failed_matches",
        None,
        failed_matches,
    ),
    FilterListEntry(
        "all",
        None,
        all_matches,
    ),
    FilterListEntry(
        "match_completed_off_plattform",
        None,
        match_completed_off_plattform,
    ),
    FilterListEntry(
        "special__support_matching",
        None,
        support_matching,
    ),
    FilterListEntry(
        "EXTRA__suggestion_match_completed_on_plattform",
        "Non-support matches that reached 8 on-platform video-call units",
        EXTRA__suggestion_match_completed_on_plattform,
    ),
    FilterListEntry(
        "EXTRA__suggestion_match_completed_off_plattform",
        "Non-support matches marked as completed off platform",
        EXTRA__suggestion_match_completed_off_plattform,
    ),
]


def get_match_list_by_name(name):
    for element in MATCH_JOURNEY_FILTERS:
        if element.name == name:
            return element
    return None


def get_match_bucket_label(bucket_name: str | None) -> str:
    if not bucket_name:
        return "Unknown"

    if bucket_name == "unknown":
        return "Unknown"

    if bucket_name == "match_journey_v2__organic_match":
        return "Organic Match"

    slug = bucket_name.split("__")[-1]
    return slug.replace("_", " ").strip().title()


MATCH_JOURNEY_CATEGORY_BUCKETS = [
    "special__support_matching",
    "match_journey_v2__organic_match",
    "match_journey_v2__unviewed",
    "match_journey_v2__one_user_viewed",
    "match_journey_v2__confirmed_no_contact",
    "match_journey_v2__confirmed_single_party_contact",
    "match_journey_v2__first_contact",
    "match_journey_v2__match_ongoing",
    "match_journey_v2__completed_match",
    "match_journey_v2__match_free_play",
    "match_journey_v2__never_confirmed",
    "match_journey_v2__no_contact",
    "match_journey_v2__user_ghosted",
    "match_journey_v2__contact_stopped",
    "match_journey_v2__reported_or_removed",
]

# Proposal filters operate on ProposedMatch and ignore the incoming Match queryset.
MATCH_BUCKET_SKIP_LISTS = frozenset(
    {
        "match_journey_v2__proposed_matches",
        "match_journey_v2__expired_proposals",
    }
)

MATCH_BUCKET_NON_STANDARD_LISTS = frozenset(
    {
        "match_journey_v2__organic_match",
    }
)


def _match_bucket_entry_applies(entry: FilterListEntry, match_pk: int) -> bool:
    if entry.queryset is None or entry.name in MATCH_BUCKET_SKIP_LISTS:
        return False
    try:
        scoped_matches = Match.objects.filter(pk=match_pk)
        if entry.name not in MATCH_BUCKET_NON_STANDARD_LISTS:
            scoped_matches = scoped_matches.filter(match_type=MatchType.STANDARD)
        return entry.queryset(scoped_matches).exists()
    except Exception:
        return False


def determine_match_buckets(match_pk, all_lists: bool = False) -> list[str]:
    bucket_names = [entry.name for entry in MATCH_JOURNEY_FILTERS] if all_lists else MATCH_JOURNEY_CATEGORY_BUCKETS
    bucket_map = {entry.name: entry for entry in MATCH_JOURNEY_FILTERS}
    return [
        name
        for name in bucket_names
        if (entry := bucket_map.get(name)) and _match_bucket_entry_applies(entry, match_pk)
    ]


def determine_match_bucket(match_pk):
    buckets = determine_match_buckets(match_pk, all_lists=False)
    return buckets[0] if buckets else None
