import logging

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

logger = logging.getLogger(__name__)


def _match_catalog_queryset(list_id: str):
    """Bind a match-journey catalog entry as a FilterListEntry queryset."""

    def fn(qs=None):
        from management.analytics.registry import get_catalog_entry

        return get_catalog_entry(list_id).queryset(Match.objects.all() if qs is None else qs)

    fn.__name__ = list_id
    fn.__qualname__ = list_id
    fn._catalog_list_id = list_id
    return fn


def _match_state_list_ids() -> tuple[str, ...]:
    """Every match-journey catalog key, served as a filter list.

    Derived from the catalog rather than re-listed: a hand-maintained copy has to be
    edited in step with the catalog, and the failure is silent — a cell the API cannot
    serve is a 500 on the funnel that requests it, not a validation error.
    ``assert_all_domains_strict`` checks the two agree.
    """
    from management.analytics.match_journey.catalog import CATALOG

    return tuple(CATALOG)


MATCH_STATE_LIST_IDS = _match_state_list_ids()

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
    # V5 partition cells (catalog-backed). V4 IDs above stay untouched.
    *[FilterListEntry(list_id, None, _match_catalog_queryset(list_id)) for list_id in MATCH_STATE_LIST_IDS],
]


def get_match_list_by_name(name):
    for element in MATCH_JOURNEY_FILTERS:
        if element.name == name:
            return element
    return None


def get_match_bucket_label(bucket_name: str | None) -> str:
    if not bucket_name or bucket_name == "unknown":
        return "Unknown"

    from management.analytics.registry import get_catalog_entry

    entry = get_catalog_entry(bucket_name)
    if entry is not None:
        return entry.display_name

    if bucket_name == "special__support_matching":
        return "Support matching"
    if bucket_name == "match_journey_v2__organic_match":
        return "Organic Match"

    slug = bucket_name.split("__")[-1]
    return slug.replace("_", " ").strip().title()


# Primary tag on match rows: support (outside V5 baseline) then exclusive V5 cells.
def _match_journey_category_buckets() -> list[str]:
    from management.analytics.match_journey.partitions import MATCH_JOURNEY_V5

    return ["special__support_matching", *MATCH_JOURNEY_V5.bucket_ids()]


def match_bucket_map(match_ids, *, matches=None) -> dict[int, str]:
    """Match ID → its primary V5 bucket, for a whole set in one classification pass.

    Support matches sit outside the partition baseline, so they are tagged separately;
    everything else comes from ``classify_partition`` (which opens ``classification_run``
    so token/inactive maps are shared). Prefer this over ``determine_match_buckets`` —
    the per-list ``.exists()`` loop re-ran inactive and success work once per cell and
    tripped Sentry N+1 on retrieve and nested user-match serialization.

    Pass ``matches`` when they already carry ``annotate_match_tokens`` so classify does
    not re-SUM LiveKit sessions for the same rows.
    """
    from management.analytics.registry import MATCH_JOURNEY_V5, classify_partition
    from management.match_success.sessions import TOTAL_CALL_TIME_ANNOTATION
    from management.match_success.versions.v1_total_minutes import tokens_from_total_minutes

    ids = list(match_ids)
    if not ids:
        return {}

    token_seed: dict[int, int] | None = None
    if matches is not None:
        token_seed = {}
        for match in matches:
            annotated = getattr(match, TOTAL_CALL_TIME_ANNOTATION, None)
            if annotated is None:
                continue
            token_seed[match.pk] = tokens_from_total_minutes(annotated.total_seconds() / 60.0)
        if not token_seed:
            token_seed = None

    scoped = Match.objects.filter(id__in=ids)
    buckets = dict.fromkeys(
        scoped.filter(support_matching=True).values_list("id", flat=True),
        "special__support_matching",
    )
    buckets.update(classify_partition(MATCH_JOURNEY_V5, scoped, token_seed=token_seed))
    return buckets


# Proposal filters operate on ProposedMatch and ignore the incoming Match queryset.
MATCH_BUCKET_SKIP_LISTS = frozenset(
    {
        "match_journey_v2__proposed_matches",
        "match_journey_v2__expired_proposals",
    }
)


def _match_bucket_entry_applies(entry: FilterListEntry, match_pk: int) -> bool:
    if entry.queryset is None or entry.name in MATCH_BUCKET_SKIP_LISTS:
        return False
    try:
        scoped_matches = Match.objects.filter(pk=match_pk)
        return entry.queryset(scoped_matches).exists()
    except Exception:
        # Logged rather than swallowed: without this a cell whose query breaks is
        # indistinguishable from a match genuinely not being in it, and the row just
        # shows no bucket (conventions §9).
        logger.exception("Match bucket list %r failed for match %s; treating as no match", entry.name, match_pk)
        return False


def determine_match_buckets(match_pk, all_lists: bool = False) -> list[str]:
    """Primary V5 bucket(s) for one match.

    **One classify pass per call** — cheaper than the old per-cell ``.exists()`` loop, but
    not a light lookup. Never call this in a loop over rows: batch the ids through
    ``match_bucket_map`` once and read from the result. The only production caller is the
    serializer fallback for single-row paths where no page-wide map exists.

    ``all_lists=True`` still walks every filter entry for debug dumps and is intentionally
    expensive.
    """
    if not all_lists:
        bucket = match_bucket_map([match_pk]).get(match_pk)
        return [bucket] if bucket else []

    bucket_names = [entry.name for entry in MATCH_JOURNEY_FILTERS]
    bucket_map = {entry.name: entry for entry in MATCH_JOURNEY_FILTERS}
    return [
        name
        for name in bucket_names
        if (entry := bucket_map.get(name)) and _match_bucket_entry_applies(entry, match_pk)
    ]


def determine_match_bucket(match_pk):
    buckets = determine_match_buckets(match_pk, all_lists=False)
    return buckets[0] if buckets else None
