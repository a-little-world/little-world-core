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
        FunnelStep(list_id="signup__all"),
        FunnelStep(list_id="signup__stage_active_adjusted"),
        FunnelStep(list_id="signup__stage_email_verified"),
        FunnelStep(list_id="signup__stage_form_completed"),
        FunnelStep(list_id="signup__stage_eligible_for_onboarding"),
        FunnelStep(list_id="signup__stage_onboarding_started"),
        FunnelStep(list_id="signup__stage_onboarded"),
    ),
)
