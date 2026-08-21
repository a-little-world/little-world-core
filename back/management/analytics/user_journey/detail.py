"""Per-user retrieve extras for the admin user-detail page.

Query semantics live in ``queries/state.py``. This module serializes a linear
stepper for one user from that partition — the same stages the V5 bucket chart
uses, so the User Card cannot disagree with the journey overview.
"""

from __future__ import annotations

from datetime import date, datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from rest_framework import serializers

from management.analytics.registry import get_catalog_entry
from management.analytics.user_journey.partitions import USER_JOURNEY_V5
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.state import State
from management.models.user import User

_DT = serializers.DateTimeField()

__all__ = ["user_journey_retrieve_extra", "user_journey_stages"]

_PHASE_BY_BUCKET = {bucket.list_id: phase.id for phase in USER_JOURNEY_V5.phases for bucket in phase.buckets}

_SIGNUP_ONBOARDING_BRANCHES = frozenset(
    {
        "state__onboarding_booked",
        "state__self_onboarding",
        "state__onboarding_no_show",
        "state__onboarding_ineligible",
    }
)
_MATCHING_PHASES = frozenset({"pre_match", "first_match", "after_failed_first"})
_SUCCESS_PHASES = frozenset({"successful_first"})
_PAST_PHASES = frozenset({"past"})
_PAST_AFTER_SUCCESS = frozenset(
    {
        "state__unresponsive_after_success",
        "state__deleted_after_success",
    }
)

_REGISTERED_LABEL = "Registered"
_PRE_FIRST_MATCH_LABEL = "Pre first match"
_IN_MATCH_LABEL = "In a match"
_AFTER_FAILED_LABEL = "After failed first match(es)"
_MATCH_SUCCESS_LABEL = "Match success"


def _fmt(value: datetime | date | None):
    """Serialize a datetime the same way DRF does on the retrieve payload."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return _DT.to_representation(value)
    return value.isoformat()


def _stage(
    *, id: str, label: str, description: str, achieved: bool, achieved_at: datetime | date | None = None
) -> dict:
    return {
        "id": id,
        "label": label,
        "description": description,
        "achieved": achieved,
        "achieved_at": _fmt(achieved_at),
    }


def _catalog(list_id: str) -> tuple[str, str]:
    entry = get_catalog_entry(list_id)
    if entry is None:
        return list_id, ""
    return entry.display_name, entry.description


def _latest_appointment_start(user: User) -> datetime | None:
    return (
        PreMatchingAppointment.objects.filter(user=user)
        .order_by("-start_time")
        .values_list("start_time", flat=True)
        .first()
    )


def _first_match_at(user: User) -> datetime | None:
    return (
        Match.objects.filter(Q(user1=user) | Q(user2=user), support_matching=False)
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )


def _onboarded_at(state: State | None) -> datetime | date | None:
    if state is None:
        return None
    if state.onboarding_call_completed_at:
        return state.onboarding_call_completed_at
    return state.self_onboarding_completed_at


def user_journey_stages(user: User, *, bucket: str | None = None, as_of: datetime | None = None) -> dict:
    """Ordered lifecycle timeline for a single user (retrieve only).

    Seven steps follow the V5 phases: registered → email verified → form completed →
    onboarding (branching signup cells) → onboarded → matching (pre-first / in-match /
    after-failed) → match success or a past-user terminal.
    """
    if bucket is None:
        from management.analytics.registry import classify_partition

        bucket = classify_partition(USER_JOURNEY_V5, User.objects.filter(pk=user.pk), as_of=as_of).get(user.pk)

    try:
        state = user.state
    except ObjectDoesNotExist:
        state = None

    phase = _PHASE_BY_BUCKET.get(bucket) if bucket else None
    email_verified = bool(state and state.email_authenticated)
    form_completed = bool(state and state.user_form_state == State.UserFormStateChoices.FILLED)
    is_onboarded = bool(state and state.is_onboarded and form_completed)
    appointment_at = _latest_appointment_start(user) if form_completed else None
    first_match_at = _first_match_at(user) if is_onboarded else None
    onboarded_at = _onboarded_at(state) if is_onboarded else None

    email_label, email_description = _catalog("funnel__email_verified")
    form_label, form_description = _catalog("funnel__form_completed")
    onboarding_label, onboarding_description = _catalog("funnel__onboarding_started")
    onboarded_label, onboarded_description = _catalog("funnel__onboarded")

    onboarding_achieved = is_onboarded or bucket in _SIGNUP_ONBOARDING_BRANCHES
    if bucket in _SIGNUP_ONBOARDING_BRANCHES:
        onboarding_label, onboarding_description = _catalog(bucket)
        onboarding_at = appointment_at
    elif bucket == "state__onboarding_not_started":
        _, onboarding_description = _catalog(bucket)
        onboarding_at = None
    else:
        onboarding_at = appointment_at or onboarded_at

    if phase in _MATCHING_PHASES and bucket:
        matching_label, matching_description = _catalog(bucket)
        matching_achieved = True
        matching_at = first_match_at
    elif is_onboarded and (phase in _SUCCESS_PHASES or bucket in _PAST_AFTER_SUCCESS):
        matching_label, matching_description = _IN_MATCH_LABEL, _catalog("state__first_match_ongoing")[1]
        matching_achieved = True
        matching_at = first_match_at
    elif is_onboarded and phase in _PAST_PHASES and first_match_at:
        matching_label, matching_description = _AFTER_FAILED_LABEL, _catalog("state__stopped_after_failed")[1]
        matching_achieved = True
        matching_at = first_match_at
    elif is_onboarded:
        matching_label, matching_description = _catalog("state__first_search_no_proposal")
        matching_achieved = True
        matching_at = None
    else:
        matching_label, matching_description = _PRE_FIRST_MATCH_LABEL, _catalog("state__first_search_no_proposal")[1]
        matching_achieved = False
        matching_at = None

    if phase in _SUCCESS_PHASES and bucket:
        outcome_label, outcome_description = _catalog(bucket)
        outcome_achieved = True
        outcome_id = "success"
    elif phase in _PAST_PHASES and bucket:
        outcome_label, outcome_description = _catalog(bucket)
        outcome_achieved = True
        outcome_id = bucket.removeprefix("state__")
    else:
        outcome_label, outcome_description = _MATCH_SUCCESS_LABEL, _catalog("state__success_idle")[1]
        outcome_achieved = False
        outcome_id = "success"

    stages = [
        _stage(
            id="registered",
            label=_REGISTERED_LABEL,
            description="Account created.",
            achieved=True,
            achieved_at=user.date_joined,
        ),
        _stage(
            id="email_verified",
            label=email_label,
            description=email_description,
            achieved=email_verified,
        ),
        _stage(
            id="form_completed",
            label=form_label,
            description=form_description,
            achieved=form_completed,
            achieved_at=state.user_form_completed_at if form_completed and state else None,
        ),
        _stage(
            id="onboarding",
            label=onboarding_label,
            description=onboarding_description,
            achieved=onboarding_achieved,
            achieved_at=onboarding_at,
        ),
        _stage(
            id="onboarded",
            label=onboarded_label,
            description=onboarded_description,
            achieved=is_onboarded,
            achieved_at=onboarded_at,
        ),
        _stage(
            id="matching",
            label=matching_label,
            description=matching_description,
            achieved=matching_achieved,
            achieved_at=matching_at,
        ),
        _stage(
            id=outcome_id,
            label=outcome_label,
            description=outcome_description,
            achieved=outcome_achieved,
        ),
    ]

    achieved_indexes = [index for index, stage in enumerate(stages) if stage["achieved"]]
    return {
        "stages": stages,
        "active_stage_index": achieved_indexes[-1] if achieved_indexes else 0,
    }


def user_journey_retrieve_extra(user: User, *, bucket: str | None = None) -> dict:
    """Read-only journey stepper for single-user GET. Not stored on User."""
    return {"journey": user_journey_stages(user, bucket=bucket)}
