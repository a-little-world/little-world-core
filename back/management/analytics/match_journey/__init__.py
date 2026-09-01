"""Match-journey analytics domain — current-state partition over ``Match``.

V4 ``match_journey_v2__*`` lists stay in the legacy filter path. They include Standard
and Random Call matches and exclude TEMPORARY lobby placeholders, matching V5.
V5 lives here under ``match_funnel__`` / ``match_state__`` (entity-qualified constructs
because ``funnel__`` / ``state__`` are already claimed by ``user_journey``).

Per-match activity (week clock, qualifying calls, streaks) lives in
``queries/activity.py``. ``detail.py`` serializes it for admin retrieve;
``snapshots.py`` is the public Match Overview subset of the same builders.
"""

from management.analytics.match_journey.partitions import MATCH_JOURNEY_V5

__all__ = ["MATCH_JOURNEY_V5"]
