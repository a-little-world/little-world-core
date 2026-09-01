"""Server-owned signup funnel shape.

This funnel uses **stage semantics**: each bar is the membership count of that
stage (users who reached it). Labels come from the catalog; overrides are rare.

Ineligibility reason subsets live in the catalog for drill-down / future
composition; they are not funnel steps.
"""

from management.analytics.core.funnels import FunnelDefinition, FunnelMode, FunnelStep
from management.models.user import User

SIGNUP_FUNNEL = FunnelDefinition(
    id="user-signup-funnel",
    title="User Signup Funnel",
    mode=FunnelMode.STAGE,
    base_model=User,
    steps=(
        FunnelStep(list_id="funnel__all"),
        FunnelStep(list_id="funnel__active_adjusted"),
        FunnelStep(list_id="funnel__email_verified"),
        FunnelStep(list_id="funnel__form_completed"),
        FunnelStep(list_id="funnel__eligible_for_onboarding"),
        FunnelStep(list_id="funnel__onboarding_started"),
        FunnelStep(list_id="funnel__onboarded"),
    ),
)
