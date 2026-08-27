"""Map legacy State.self_onboarding_* fields onto UserCourseProgress.

State stored the last completed quiz step id (e.g. self_onboarding_c1_q_1).
UserCourseProgress stores the chapter the user is currently on.
"""

from datetime import datetime, time

from django.db.models import Prefetch, Q
from django.utils import timezone

from management.models.courses import Course, UserCourseProgress

#: Attribute ``self_onboarding_progress_prefetch`` writes and
#: ``self_onboarding_completed_at_for_user`` reads. One name, one place.
SELF_ONBOARDING_PROGRESS_ATTR = "self_onboarding_progress_rows"

LEGACY_QUIZ_STEP_TO_CHAPTER = {
    "self_onboarding_c1_q_1": "self_onboarding_c1",
    "self_onboarding_c2_q_1": "self_onboarding_c2",
    "self_onboarding_c3_q_1": "self_onboarding_c3",
}

FALLBACK_CHAPTER_IDS = ["self_onboarding_c1", "self_onboarding_c2", "self_onboarding_c3"]


def chapter_ids_for_course(course: Course) -> list[str]:
    ids = list(course.chapters.order_by("order").values_list("chapter_id", flat=True))
    return ids or list(FALLBACK_CHAPTER_IDS)


def legacy_state_has_progress(state) -> bool:
    return bool(
        state.self_onboarding_started
        or state.self_onboarding_completed
        or (state.self_onboarding_step_id or "").strip()
    )


def _aware_start_of_day(d):
    dt = datetime.combine(d, time.min)
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def infer_completed_at(state):
    """Completion time, or None when State never recorded one.

    No ``timezone.now()`` fallback. A state flagged completed with no date would take the
    backfill *run* date, and ``self_onboarding_completed_at_for_user`` prefers the
    progress row over State — so the invented date would put the user in the wrong
    onboarded-month cohort and zero their match waiting time. None leaves the row
    honestly undated; ``avg_days_to_complete`` already filters ``completed_at__isnull``.
    """
    if state.self_onboarding_completed_at:
        return _aware_start_of_day(state.self_onboarding_completed_at)
    return None


def infer_started_at(state):
    """Best available start time for a backfilled row.

    State never stored one. ``user_form_completed_at`` is the earliest point the
    walkthrough could have been opened, so it is the closest proxy there is;
    ``created_at`` covers rows predating that field. Clamped to the completion date,
    since a start after the finish would make ``avg_days_to_complete`` negative.

    Deliberately *not* the completion date first: that gave every completed row
    ``started_at == completed_at`` and collapsed ``avg_days_to_complete`` to ~0. The
    result is an upper bound on how long the course took — someone who signed up in
    March and did the walkthrough in June reads as a three-month course.
    """
    completed_at = infer_completed_at(state)
    candidate = state.user_form_completed_at or state.created_at
    if completed_at is None:
        return candidate
    if candidate is None or candidate > completed_at:
        return completed_at
    return candidate


def resolve_completed_chapter_id(step_id: str, chapter_ids: list[str]) -> str | None:
    stored = (step_id or "").strip()
    if not stored:
        return None
    if stored in LEGACY_QUIZ_STEP_TO_CHAPTER:
        chapter_id = LEGACY_QUIZ_STEP_TO_CHAPTER[stored]
        return chapter_id if chapter_id in chapter_ids else None
    if stored in chapter_ids:
        return stored
    for suffix in ("_q_1", "_q_2", "_q_3"):
        if stored.endswith(suffix):
            chapter_id = stored[: -len(suffix)]
            if chapter_id in chapter_ids:
                return chapter_id
    return None


def progress_fields_from_legacy_state(state, chapter_ids: list[str]) -> dict | None:
    """Return fields for UserCourseProgress, or None if State has no walkthrough activity."""
    if not legacy_state_has_progress(state):
        return None

    completed = bool(state.self_onboarding_completed)
    completed_chapter_id = resolve_completed_chapter_id(state.self_onboarding_step_id, chapter_ids)

    current_chapter_id = ""
    current_step_index = 0

    if completed_chapter_id and chapter_ids:
        idx = chapter_ids.index(completed_chapter_id)
        if idx + 1 < len(chapter_ids) and not completed:
            current_chapter_id = chapter_ids[idx + 1]
        else:
            current_chapter_id = chapter_ids[idx]
            if idx + 1 >= len(chapter_ids):
                completed = True

    if completed and not current_chapter_id and chapter_ids:
        current_chapter_id = chapter_ids[-1]

    fields = {
        "current_chapter_id": current_chapter_id,
        "current_step_index": current_step_index,
        "completed": completed,
        "completed_at": infer_completed_at(state) if completed else None,
        "started_at": infer_started_at(state),
    }
    return fields


def hydrate_progress_from_legacy_state(progress: UserCourseProgress, state) -> bool:
    """Copy State walkthrough fields onto a newly created progress row. Returns True if applied."""
    fields = progress_fields_from_legacy_state(state, chapter_ids_for_course(progress.course))
    if not fields:
        return False
    started_at = fields.pop("started_at")
    for name, value in fields.items():
        setattr(progress, name, value)
    progress.save(update_fields=["current_chapter_id", "current_step_index", "completed", "completed_at"])
    if started_at is not None:
        UserCourseProgress.objects.filter(pk=progress.pk).update(started_at=started_at)
        progress.started_at = started_at
    return True


def self_onboarding_in_progress_q():
    """User filter: walkthrough started and not finished (course progress or legacy State)."""
    return UserCourseProgress.exists_for_user(slug=Course.SELF_ONBOARDING_SLUG, completed=False) | Q(
        state__self_onboarding_started=True,
        state__self_onboarding_completed=False,
    )


def self_onboarding_started_q():
    """User filter: any self-onboarding activity (course progress or legacy State)."""
    return UserCourseProgress.exists_for_user(slug=Course.SELF_ONBOARDING_SLUG) | Q(state__self_onboarding_started=True)


def self_onboarding_progress_prefetch(prefix: str = "") -> Prefetch:
    """Prefetch that lets ``self_onboarding_completed_at_for_user`` skip its per-user query.

    Every queryset whose rows that helper is called on needs this. Without it the helper
    silently falls back to one query per user, which is how the cohort and first-proposal
    loops in ``match_proposal_stats`` each came to run thousands of them. ``prefix`` walks
    a relation first, e.g. ``"confirming_user__"``.
    """
    return Prefetch(
        f"{prefix}course_progress",
        queryset=UserCourseProgress.objects.filter(
            course__slug=Course.SELF_ONBOARDING_SLUG,
            completed=True,
        ),
        to_attr=SELF_ONBOARDING_PROGRESS_ATTR,
    )


def self_onboarding_completed_at_for_user(user):
    """Datetime the user finished the walkthrough, or None.

    Prefers UserCourseProgress; falls back to State.self_onboarding_completed_at
    (start of that calendar day) until the backfill has run.
    """
    prefetched = getattr(user, SELF_ONBOARDING_PROGRESS_ATTR, None)
    if prefetched is not None:
        progress = prefetched[0] if prefetched else None
    else:
        progress = (
            UserCourseProgress.objects.filter(user=user, course__slug=Course.SELF_ONBOARDING_SLUG, completed=True)
            .only("completed_at")
            .first()
        )
    if progress is not None and progress.completed_at is not None:
        return progress.completed_at
    completed_date = user.state.self_onboarding_completed_at
    if completed_date is not None:
        return _aware_start_of_day(completed_date)
    return None


def self_onboarding_user_payload(user) -> dict:
    """Fields exposed on GET /api/user for the walkthrough selection card."""
    progress = UserCourseProgress.objects.filter(user=user, course__slug=Course.SELF_ONBOARDING_SLUG).first()
    if progress is not None:
        return {
            "selfOnboardingCompleted": progress.completed,
            "selfOnboardingStarted": True,
            "selfOnboardingStepId": progress.current_chapter_id or "",
            "selfOnboardingProgress": progress.progress_fraction(),
        }
    state = user.state
    if state.self_onboarding_completed:
        fraction = 1.0
    else:
        step = (state.self_onboarding_step_id or "").strip()
        chapter_id = LEGACY_QUIZ_STEP_TO_CHAPTER.get(step)
        if chapter_id and chapter_id in FALLBACK_CHAPTER_IDS:
            fraction = (FALLBACK_CHAPTER_IDS.index(chapter_id) + 1) / float(len(FALLBACK_CHAPTER_IDS))
        else:
            fraction = 0.0
    return {
        "selfOnboardingCompleted": state.self_onboarding_completed,
        "selfOnboardingStarted": state.self_onboarding_started,
        "selfOnboardingStepId": state.self_onboarding_step_id or "",
        "selfOnboardingProgress": fraction,
    }
