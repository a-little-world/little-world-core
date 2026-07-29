from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import QuerySet

from management.models.profile import Profile


@dataclass(frozen=True)
class CohortSpec:
    """Universe of users for signup funnel counting — applied once before buckets."""

    start_date: date | str
    end_date: date | str | datetime
    volunteers_only: bool = False
    include_too_low_german_level: bool = True


def _end_inclusive(end_date: date | str | datetime) -> datetime:
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    if isinstance(end_date, datetime):
        return end_date
    return datetime.combine(end_date, datetime.max.time())


def apply_cohort(qs: QuerySet, spec: CohortSpec) -> QuerySet:
    """Filter to signup-date cohort and optional segment gates."""
    end = _end_inclusive(spec.end_date)
    start = spec.start_date
    if isinstance(start, str):
        start = datetime.strptime(start, "%Y-%m-%d").date()

    qs = qs.filter(date_joined__range=[start, end])

    if spec.volunteers_only:
        qs = qs.filter(profile__user_type=Profile.TypeChoices.VOLUNTEER)

    if not spec.include_too_low_german_level:
        qs = qs.exclude(
            profile__user_type=Profile.TypeChoices.LEARNER,
            profile__lang_skill__contains=[
                {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}
            ],
        )

    return qs
