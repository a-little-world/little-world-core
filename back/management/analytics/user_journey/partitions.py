"""User-journey V5 partition definition.

Partition types live in ``analytics.core.partitions`` (promoted when match journey
became the second caller — conventions §1).
"""

from management.analytics.core.partitions import (
    PARTITION_ALLOWED_ROLES,
    PartitionBucket,
    PartitionDefinition,
    PartitionPhase,
)
from management.models.user import User

__all__ = [
    "PARTITION_ALLOWED_ROLES",
    "USER_JOURNEY_V5",
    "PartitionBucket",
    "PartitionDefinition",
    "PartitionPhase",
]

USER_JOURNEY_V5 = PartitionDefinition(
    id="user-journey-v5",
    title="The User Journey V5",
    description=(
        "Current state of every user who signed up in the selected period. Each user is "
        "counted in exactly one bucket, so the buckets sum to the total."
    ),
    base_model=User,
    baseline_list_id="funnel__all",
    phases=(
        PartitionPhase(
            id="signup",
            title="Sign-up",
            buckets=(
                PartitionBucket(list_id="state__email_unverified"),
                PartitionBucket(list_id="state__form_unfilled"),
                PartitionBucket(list_id="state__onboarding_not_started"),
                PartitionBucket(list_id="state__onboarding_booked"),
                PartitionBucket(list_id="state__self_onboarding"),
                PartitionBucket(list_id="state__onboarding_no_show"),
                PartitionBucket(list_id="state__onboarding_ineligible"),
            ),
        ),
        PartitionPhase(
            id="pre_match",
            title="Pre first match",
            buckets=(
                PartitionBucket(list_id="state__gave_up"),
                PartitionBucket(list_id="state__first_search_no_proposal"),
                PartitionBucket(list_id="state__first_search_proposal_expired"),
                PartitionBucket(list_id="state__first_search_rejected_by_them"),
                PartitionBucket(list_id="state__first_search_rejected_by_partner"),
                PartitionBucket(list_id="state__first_search_proposal_closed"),
                PartitionBucket(list_id="state__search_blocked"),
                PartitionBucket(list_id="state__proposed"),
            ),
        ),
        PartitionPhase(
            id="first_match",
            title="In a match (Pre-first success)",
            buckets=(
                PartitionBucket(list_id="state__first_match_kickoff"),
                PartitionBucket(list_id="state__first_match_ongoing"),
            ),
        ),
        PartitionPhase(
            id="after_failed_first",
            title="After failed first match(es)",
            buckets=(
                PartitionBucket(list_id="state__rematch_proposed"),
                PartitionBucket(list_id="state__searching_after_failed"),
                PartitionBucket(list_id="state__stopped_after_failed"),
            ),
        ),
        PartitionPhase(
            id="successful_first",
            title="At least one successful match",
            buckets=(
                PartitionBucket(list_id="state__success_ongoing_searching"),
                PartitionBucket(list_id="state__success_ongoing_settled"),
                PartitionBucket(list_id="state__success_searching"),
                PartitionBucket(list_id="state__success_idle"),
            ),
        ),
        PartitionPhase(
            id="past",
            title="Past users",
            buckets=(
                PartitionBucket(list_id="state__unresponsive_after_success"),
                PartitionBucket(list_id="state__unresponsive"),
                PartitionBucket(list_id="state__deleted_after_success"),
                PartitionBucket(list_id="state__deleted"),
                PartitionBucket(list_id="state__record_incomplete"),
            ),
        ),
    ),
)
