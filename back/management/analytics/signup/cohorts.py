from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Model, QuerySet

from management.analytics.core.cohorts import CohortSpec
from management.analytics.core.display_time import inclusive_range
from management.models.profile import Profile
from management.models.user import User


@dataclass(frozen=True)
class SignupCohort:
    """Universe of users for signup funnel counting — applied once before buckets.

    Range semantics: **joined within the range**, both bounds inclusive, interpreted in
    the display timezone (conventions §10). Callers should validate and parse request
    input before constructing this — the view owns transport (§11).
    """

    start_date: date | datetime | str
    end_date: date | datetime | str
    volunteers_only: bool = False
    include_too_low_german_level: bool = True

    @property
    def base_model(self) -> type[Model]:
        return User

    def apply(self, qs: QuerySet) -> QuerySet:
        """Filter to signup-date cohort and optional segment gates."""
        start, end = inclusive_range(self.start_date, self.end_date)

        qs = qs.filter(date_joined__range=[start, end])

        if self.volunteers_only:
            qs = qs.filter(profile__user_type=Profile.TypeChoices.VOLUNTEER)

        if not self.include_too_low_german_level:
            qs = qs.exclude(
                profile__user_type=Profile.TypeChoices.LEARNER,
                profile__lang_skill__contains=[
                    {"lang": Profile.LanguageChoices.GERMAN, "level": Profile.LanguageSkillChoices.LEVEL_0}
                ],
            )

        return qs


def apply_cohort(qs: QuerySet, spec: CohortSpec) -> QuerySet:
    """Apply a cohort spec to a queryset (signup or any ``CohortSpec`` implementation)."""
    return spec.apply(qs)
