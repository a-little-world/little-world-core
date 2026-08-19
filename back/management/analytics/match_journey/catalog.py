"""Match-journey catalog — ``match_funnel__`` baseline + ``match_state__`` cells."""

from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.roles import CatalogRole
from management.analytics.match_journey.queries import state as s
from management.models.matches import Match

_MATCH = Match

DOMAIN_PREFIXES = ("match_funnel__", "match_state__")

_IN_FLIGHT_MEMBERS = tuple(f"match_state__tokens_{n}" for n in range(8))
_FAILED_TOKEN_MEMBERS = tuple(f"match_state__failed_tokens_{n}" for n in range(8))

CATALOG: dict[str, CatalogEntry] = {
    "match_funnel__all": CatalogEntry(
        list_id="match_funnel__all",
        role=CatalogRole.BASELINE,
        queryset=s.all_matches,
        description="All non-support Standard and Random Call matches in the selected cohort (all-time if no dates).",
        display_name="All matches",
        base_model=_MATCH,
    ),
    # --- Kickoff ---
    "match_state__unviewed": CatalogEntry(
        list_id="match_state__unviewed",
        role=CatalogRole.STAGE,
        queryset=s.kickoff_unviewed,
        description="Active match, neither user has confirmed yet (within the 10-week activity window).",
        display_name="Unviewed",
        base_model=_MATCH,
    ),
    "match_state__one_viewed": CatalogEntry(
        list_id="match_state__one_viewed",
        role=CatalogRole.STAGE,
        queryset=s.kickoff_one_viewed,
        description="Active match confirmed by one user only (within the 10-week activity window).",
        display_name="One user viewed",
        base_model=_MATCH,
    ),
    "match_state__confirmed_no_contact": CatalogEntry(
        list_id="match_state__confirmed_no_contact",
        role=CatalogRole.STAGE,
        queryset=s.kickoff_confirmed_no_contact,
        description="Both confirmed; no messages and no video calls yet.",
        display_name="Confirmed - no contact",
        base_model=_MATCH,
    ),
    "match_state__confirmed_one_way": CatalogEntry(
        list_id="match_state__confirmed_one_way",
        role=CatalogRole.STAGE,
        queryset=s.kickoff_confirmed_one_way,
        description="Both confirmed; only one side has messaged.",
        display_name="Confirmed - one-way contact",
        base_model=_MATCH,
    ),
    "match_state__both_contacted_no_video": CatalogEntry(
        list_id="match_state__both_contacted_no_video",
        role=CatalogRole.STAGE,
        queryset=s.kickoff_both_contacted_no_video,
        description=(
            "Both confirmed and messaged each other, but no mutual video call yet. "
            "Distinct from 0 tokens (which requires a call)."
        ),
        display_name="Both contacted - no video",
        base_model=_MATCH,
    ),
    # --- In flight (COMPOSITE + cells) ---
    "match_state__in_flight": CatalogEntry(
        list_id="match_state__in_flight",
        role=CatalogRole.COMPOSITE,
        queryset=s.in_flight,
        description="Matches with video airtime, under 8 tokens, still active within 10 weeks.",
        display_name="In flight (not yet successful)",
        base_model=_MATCH,
        members=_IN_FLIGHT_MEMBERS,
    ),
    **{
        f"match_state__tokens_{n}": CatalogEntry(
            list_id=f"match_state__tokens_{n}",
            role=CatalogRole.STAGE,
            queryset=getattr(s, f"in_flight_tokens_{n}"),
            description=f"In flight with exactly {n} match token(s).",
            display_name=f"{n} tokens",
            base_model=_MATCH,
        )
        for n in range(8)
    },
    # --- Success ---
    "match_state__success_engaged": CatalogEntry(
        list_id="match_state__success_engaged",
        role=CatalogRole.STAGE,
        queryset=s.success_engaged,
        description="Still active; reached 8+ tokens and had a message or call within the last 4 weeks.",
        display_name="Successful - engaged",
        base_model=_MATCH,
    ),
    "match_state__success_dormant": CatalogEntry(
        list_id="match_state__success_dormant",
        role=CatalogRole.STAGE,
        queryset=s.success_dormant,
        description="Still active; reached 8+ tokens but no message or call within the last 4 weeks.",
        display_name="Successful - dormant",
        base_model=_MATCH,
    ),
    "match_state__success_off_platform": CatalogEntry(
        list_id="match_state__success_off_platform",
        role=CatalogRole.STAGE,
        queryset=s.success_off_platform,
        description="Still active; marked completed off platform.",
        display_name="Successful - off platform",
        base_model=_MATCH,
    ),
    # --- Inactive: how it ended × stage reached ---
    "match_state__reported_successful": CatalogEntry(
        list_id="match_state__reported_successful",
        role=CatalogRole.DROPOUT,
        queryset=s.reported_successful,
        description=(
            "Inactive because a user reported the other; it had already reached success (8+ tokens or off-platform)."
        ),
        display_name="Reported - after success",
        base_model=_MATCH,
    ),
    "match_state__reported_before_success": CatalogEntry(
        list_id="match_state__reported_before_success",
        role=CatalogRole.DROPOUT,
        queryset=s.reported_before_success,
        description=(
            "Inactive because a user reported the other; it was in flight (had mutual video, under 8 tokens)."
        ),
        display_name="Reported - before success",
        base_model=_MATCH,
    ),
    "match_state__reported_kickoff": CatalogEntry(
        list_id="match_state__reported_kickoff",
        role=CatalogRole.DROPOUT,
        queryset=s.reported_kickoff,
        description=("Inactive because a user reported the other; it was still in kickoff (no mutual video yet)."),
        display_name="Reported - during kickoff",
        base_model=_MATCH,
    ),
    "match_state__unmatched_successful": CatalogEntry(
        list_id="match_state__unmatched_successful",
        role=CatalogRole.DROPOUT,
        queryset=s.unmatched_successful,
        description=(
            "Inactive because someone deliberately ended the match; it had already reached success (8+ tokens or off-platform)."
        ),
        display_name="Unmatched - after success",
        base_model=_MATCH,
    ),
    "match_state__unmatched_before_success": CatalogEntry(
        list_id="match_state__unmatched_before_success",
        role=CatalogRole.DROPOUT,
        queryset=s.unmatched_before_success,
        description=(
            "Inactive because someone deliberately ended the match; it was in flight (had mutual video, under 8 tokens)."
        ),
        display_name="Unmatched - before success",
        base_model=_MATCH,
    ),
    "match_state__unmatched_kickoff": CatalogEntry(
        list_id="match_state__unmatched_kickoff",
        role=CatalogRole.DROPOUT,
        queryset=s.unmatched_kickoff,
        description=(
            "Inactive because someone deliberately ended the match; it was still in kickoff (no mutual video yet)."
        ),
        display_name="Unmatched - during kickoff",
        base_model=_MATCH,
    ),
    "match_state__account_deleted_successful": CatalogEntry(
        list_id="match_state__account_deleted_successful",
        role=CatalogRole.DROPOUT,
        queryset=s.account_deleted_successful,
        description=(
            "Inactive because a participant's account was deleted; it had already reached success (8+ tokens or off-platform)."
        ),
        display_name="Account deleted - after success",
        base_model=_MATCH,
    ),
    "match_state__account_deleted_before_success": CatalogEntry(
        list_id="match_state__account_deleted_before_success",
        role=CatalogRole.DROPOUT,
        queryset=s.account_deleted_before_success,
        description=(
            "Inactive because a participant's account was deleted; it was in flight (had mutual video, under 8 tokens)."
        ),
        display_name="Account deleted - before success",
        base_model=_MATCH,
    ),
    "match_state__account_deleted_kickoff": CatalogEntry(
        list_id="match_state__account_deleted_kickoff",
        role=CatalogRole.DROPOUT,
        queryset=s.account_deleted_kickoff,
        description=(
            "Inactive because a participant's account was deleted; it was still in kickoff (no mutual video yet)."
        ),
        display_name="Account deleted - during kickoff",
        base_model=_MATCH,
    ),
    "match_state__ghosted_successful": CatalogEntry(
        list_id="match_state__ghosted_successful",
        role=CatalogRole.DROPOUT,
        queryset=s.ghosted_successful,
        description=(
            "Inactive because a participant was flagged as ghosting; it had already reached success (8+ tokens or off-platform)."
        ),
        display_name="Ghosted - after success",
        base_model=_MATCH,
    ),
    "match_state__ghosted_before_success": CatalogEntry(
        list_id="match_state__ghosted_before_success",
        role=CatalogRole.DROPOUT,
        queryset=s.ghosted_before_success,
        description=(
            "Inactive because a participant was flagged as ghosting; it was in flight (had mutual video, under 8 tokens)."
        ),
        display_name="Ghosted - before success",
        base_model=_MATCH,
    ),
    "match_state__ghosted_kickoff": CatalogEntry(
        list_id="match_state__ghosted_kickoff",
        role=CatalogRole.DROPOUT,
        queryset=s.ghosted_kickoff,
        description=(
            "Inactive because a participant was flagged as ghosting; it was still in kickoff (no mutual video yet)."
        ),
        display_name="Ghosted - during kickoff",
        base_model=_MATCH,
    ),
    "match_state__unrecorded_successful": CatalogEntry(
        list_id="match_state__unrecorded_successful",
        role=CatalogRole.DROPOUT,
        queryset=s.unrecorded_successful,
        description=(
            "Inactive with no (or malformed) ``report_unmatch`` entry, so why it ended is unknown; it had already reached success (8+ tokens or off-platform). A data-quality signal, not an outcome someone chose."
        ),
        display_name="No closing record - after success",
        base_model=_MATCH,
    ),
    "match_state__unrecorded_before_success": CatalogEntry(
        list_id="match_state__unrecorded_before_success",
        role=CatalogRole.DROPOUT,
        queryset=s.unrecorded_before_success,
        description=(
            "Inactive with no (or malformed) ``report_unmatch`` entry, so why it ended is unknown; it was in flight (had mutual video, under 8 tokens). A data-quality signal, not an outcome someone chose."
        ),
        display_name="No closing record - before success",
        base_model=_MATCH,
    ),
    "match_state__unrecorded_kickoff": CatalogEntry(
        list_id="match_state__unrecorded_kickoff",
        role=CatalogRole.DROPOUT,
        queryset=s.unrecorded_kickoff,
        description=(
            "Inactive with no (or malformed) ``report_unmatch`` entry, so why it ended is unknown; it was still in kickoff (no mutual video yet). A data-quality signal, not an outcome someone chose."
        ),
        display_name="No closing record - during kickoff",
        base_model=_MATCH,
    ),
    # --- Failed (active, 10-week cliff) ---
    "match_state__failed_unviewed": CatalogEntry(
        list_id="match_state__failed_unviewed",
        role=CatalogRole.DROPOUT,
        queryset=s.failed_unviewed,
        description="No activity for 10+ weeks; never confirmed.",
        display_name="Failed - unviewed",
        base_model=_MATCH,
    ),
    "match_state__failed_one_viewed": CatalogEntry(
        list_id="match_state__failed_one_viewed",
        role=CatalogRole.DROPOUT,
        queryset=s.failed_one_viewed,
        description="No activity for 10+ weeks; only one user confirmed.",
        display_name="Failed - one viewed",
        base_model=_MATCH,
    ),
    "match_state__failed_confirmed_no_contact": CatalogEntry(
        list_id="match_state__failed_confirmed_no_contact",
        role=CatalogRole.DROPOUT,
        queryset=s.failed_confirmed_no_contact,
        description="No activity for 10+ weeks; confirmed but never contacted.",
        display_name="Failed - no contact",
        base_model=_MATCH,
    ),
    "match_state__failed_confirmed_one_way": CatalogEntry(
        list_id="match_state__failed_confirmed_one_way",
        role=CatalogRole.DROPOUT,
        queryset=s.failed_confirmed_one_way,
        description="No activity for 10+ weeks; stuck at one-way contact.",
        display_name="Failed - one-way contact",
        base_model=_MATCH,
    ),
    "match_state__failed_both_contacted_no_video": CatalogEntry(
        list_id="match_state__failed_both_contacted_no_video",
        role=CatalogRole.DROPOUT,
        queryset=s.failed_both_contacted_no_video,
        description="No activity for 10+ weeks; messaged both ways but never video-called.",
        display_name="Failed - both contacted, no video",
        base_model=_MATCH,
    ),
    **{
        f"match_state__failed_tokens_{n}": CatalogEntry(
            list_id=f"match_state__failed_tokens_{n}",
            role=CatalogRole.DROPOUT,
            queryset=getattr(s, f"failed_tokens_{n}"),
            description=(f"No activity for 10+ weeks with exactly {n} token(s) - stalled before success."),
            display_name=f"Failed - {n} tokens",
            base_model=_MATCH,
        )
        for n in range(8)
    },
    "match_state__unclassifiable": CatalogEntry(
        list_id="match_state__unclassifiable",
        role=CatalogRole.DROPOUT,
        queryset=s.unclassifiable,
        description="Active non-support match that fits no other cell. Non-zero means a gap to fix.",
        display_name="Unclassifiable",
        base_model=_MATCH,
    ),
}


def _assert_catalog_prefixes() -> None:
    for key in CATALOG:
        if not key.startswith(DOMAIN_PREFIXES):
            raise ValueError(f"Catalog key {key!r} must start with one of {DOMAIN_PREFIXES!r}")


_assert_catalog_prefixes()
