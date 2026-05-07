from dataclasses import dataclass, field
from typing import Literal

from .registry import register, register_task_type


def _get_user(user_id: int):
    from management.models.user import User

    return User.objects.select_related("state").get(id=user_id)


def _tag_user(user, tag: str) -> None:
    state = user.state
    tags = list(state.tags) if state.tags else []
    if tag not in tags:
        tags.append(tag)
        state.tags = tags
        state.save(update_fields=["tags"])


def _contact_user(user, message: str) -> None:
    from management.controller import get_base_management_user

    management_user = get_base_management_user()
    management_user.message(user, message)


# ─── scoring_profile_assessment ───────────────────────────────────────────────


@dataclass
class ScoringAssessmentStaticParams:
    user_id: int


@dataclass
class ScoringAssessmentParams:
    decision: Literal["approve", "flag", "contact_user"] = "approve"
    contact_message: str = ""


@register("scoring_profile_assessment", static_schema=ScoringAssessmentStaticParams, param_schema=ScoringAssessmentParams)
def scoring_profile_assessment(static_params: dict, params: dict) -> None:
    """Admin reviews a profile flagged by the scoring system.

    static_params:
        user_id (int)

    params:
        decision (str): 'approve' | 'flag' | 'contact_user'
        contact_message (str, optional): message to send if decision == 'contact_user'
    """
    decision = params.get("decision", "approve")
    if decision == "flag":
        user = _get_user(static_params["user_id"])
        _tag_user(user, "scoring_flagged")
    elif decision == "contact_user":
        user = _get_user(static_params["user_id"])
        msg = params.get("contact_message", "")
        if msg:
            _contact_user(user, msg)


# ─── profile_action_suspicious_profile ────────────────────────────────────────


@dataclass
class SuspiciousProfileStaticParams:
    user_id: int
    reason: str


@dataclass
class SuspiciousProfileParams:
    decision: Literal["tag_suspicious", "contact_user", "dismiss"] = "dismiss"
    contact_message: str = ""


@register("profile_action_suspicious_profile", static_schema=SuspiciousProfileStaticParams, param_schema=SuspiciousProfileParams)
def profile_action_suspicious_profile(static_params: dict, params: dict) -> None:
    """Admin reviews a profile flagged as suspicious.

    static_params:
        user_id (int)
        reason (str): why it was flagged

    params:
        decision (str): 'tag_suspicious' | 'contact_user' | 'dismiss'
        contact_message (str, optional)
    """
    decision = params.get("decision", "dismiss")
    if decision == "tag_suspicious":
        user = _get_user(static_params["user_id"])
        _tag_user(user, "suspicious")
    elif decision == "contact_user":
        user = _get_user(static_params["user_id"])
        msg = params.get("contact_message", "")
        if msg:
            _contact_user(user, msg)


# ─── profile_action_too_empty_profile ─────────────────────────────────────────


@dataclass
class TooEmptyProfileStaticParams:
    user_id: int
    missing_fields: list


@dataclass
class TooEmptyProfileParams:
    decision: Literal["contact_user", "dismiss"] = "dismiss"
    contact_message: str = field(default="")


@register("profile_action_too_empty_profile", static_schema=TooEmptyProfileStaticParams, param_schema=TooEmptyProfileParams)
def profile_action_too_empty_profile(static_params: dict, params: dict) -> None:
    """Admin reviews a profile flagged as too empty.

    static_params:
        user_id (int)
        missing_fields (list[str])

    params:
        decision (str): 'contact_user' | 'dismiss'
        contact_message (str, optional)
    """
    decision = params.get("decision", "dismiss")
    if decision == "contact_user":
        user = _get_user(static_params["user_id"])
        msg = params.get("contact_message", "")
        if msg:
            _contact_user(user, msg)


# ─── Task type registrations ───────────────────────────────────────────────────

register_task_type(
    "scoring_assessment",
    action_type="scoring_profile_assessment",
    task_title=lambda s: f"Profile scoring review — user #{s['user_id']}",
)

register_task_type(
    "suspicious_profile",
    action_type="profile_action_suspicious_profile",
    task_title=lambda s: f"Suspicious profile — user #{s['user_id']}",
    task_description=lambda s: f"Profile flagged: {s['reason']}",
)

register_task_type(
    "too_empty_profile",
    action_type="profile_action_too_empty_profile",
    task_title=lambda s: f"Incomplete profile — user #{s['user_id']}",
    task_description=lambda s: f"Profile is missing: {', '.join(s['missing_fields'])}",
)
