"""Match Journey V5 partition definition."""

from management.analytics.core.partitions import PartitionBucket, PartitionDefinition, PartitionPhase
from management.analytics.match_journey.queries.state import (
    CLOSING_KINDS,
    ENGAGEMENT_DAYS,
    FAILURE_CLIFF_DAYS,
    STAGES,
)
from management.models.matches import Match

_ENGAGEMENT_WEEKS = ENGAGEMENT_DAYS // 7
_FAILURE_WEEKS = FAILURE_CLIFF_DAYS // 7

MATCH_JOURNEY_V5 = PartitionDefinition(
    id="match-journey-v5",
    title="The Match Journey V5",
    description=(
        "Current state of every non-support match in the selected cohort. Each match is "
        "counted in exactly one bucket. Success is 8+ tokens (or off-platform) while still "
        f"active. Two clocks then split those outcomes: a successful match is dormant after "
        f"{_ENGAGEMENT_WEEKS} weeks without a message or call, and a still-active match that "
        f"never reached success is failed after {_FAILURE_WEEKS} weeks without activity. A "
        "closed match that had already reached success counts as Successful, not Unmatched "
        "or Removed — that phase is reported/removed matches that never got there."
    ),
    base_model=Match,
    baseline_list_id="match_funnel__all",
    phases=(
        PartitionPhase(
            id="kickoff",
            title="Kickoff",
            buckets=(
                PartitionBucket(list_id="match_state__unviewed"),
                PartitionBucket(list_id="match_state__one_viewed"),
                PartitionBucket(list_id="match_state__confirmed_no_contact"),
                PartitionBucket(list_id="match_state__confirmed_one_way"),
                PartitionBucket(list_id="match_state__both_contacted_no_video"),
            ),
        ),
        PartitionPhase(
            id="in_flight",
            title="In flight",
            buckets=tuple(PartitionBucket(list_id=f"match_state__tokens_{n}") for n in range(8)),
        ),
        PartitionPhase(
            id="successful",
            title="Successful",
            # Still-active successes, plus matches that had already reached success before
            # they were reported/unmatched/deleted/ghosted or closed with no record — every
            # match that ever succeeded belongs here, not split off by what happened after.
            buckets=(
                PartitionBucket(list_id="match_state__success_engaged"),
                PartitionBucket(list_id="match_state__success_dormant"),
                PartitionBucket(list_id="match_state__success_off_platform"),
                *tuple(PartitionBucket(list_id=f"match_state__{kind}_successful") for kind in CLOSING_KINDS),
            ),
        ),
        PartitionPhase(
            id="failed",
            title="Failed",
            buckets=(
                PartitionBucket(list_id="match_state__failed_unviewed"),
                PartitionBucket(list_id="match_state__failed_one_viewed"),
                PartitionBucket(list_id="match_state__failed_confirmed_no_contact"),
                PartitionBucket(list_id="match_state__failed_confirmed_one_way"),
                PartitionBucket(list_id="match_state__failed_both_contacted_no_video"),
                *tuple(PartitionBucket(list_id=f"match_state__failed_tokens_{n}") for n in range(8)),
            ),
        ),
        PartitionPhase(
            id="inactive",
            title="Unmatched or Removed",
            # Closing kind × stage reached, excluding the "successful" stage — those sit in
            # the Successful phase above instead (a match that already succeeded belongs
            # with every other success, not with the ones that never got there). "Removed"
            # used to absorb every non-report ending, including 168 matches with no closing
            # record at all - which read as a deliberate removal nobody actually performed.
            buckets=tuple(
                PartitionBucket(list_id=f"match_state__{kind}_{stage}")
                for kind in CLOSING_KINDS
                for stage in STAGES
                if stage != "successful"
            ),
        ),
        PartitionPhase(
            id="other",
            title="Other",
            buckets=(PartitionBucket(list_id="match_state__unclassifiable"),),
        ),
    ),
)
