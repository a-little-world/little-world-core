"""Offering, answering and expiring in-app surveys.

Eligibility is evaluated when the user is actually in the app, never precomputed into a
frozen cohort: a user who gains the company field next week is included automatically, and a
user who never returns leaves no row behind.

Delivery is the polled pending endpoint and nothing else. WebSocket-only delivery is what
failed silently for a year, so the ``event:call_ended`` trigger *creates* an offer and the
next poll finds it — which also removes the "only if the user is connected" limitation.
"""

from datetime import datetime, time, timedelta
from uuid import uuid4

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import DurationField, ExpressionWrapper, F, Max, Q
from django.utils import timezone

from management.models.custom_banner_event_filters import FILTER_FUNC_MAP, CustomFilterChoices
from management.models.survey import (
    MAX_TEXT_ANSWER_LENGTH,
    QUALIFYING_CALL_MAX_DURATION,
    QuestionType,
    SurveyCampaign,
    SurveyResponse,
    build_context_key,
    option_values,
)

POST_CALL_SLUG = "post-call"

#: Quiet period after a user is shown any survey card, across every campaign.
#:
#: Deliberately user-wide rather than per offer. The client refetches the pending endpoint as
#: soon as a survey closes, so a per-offer rule hands the user the next campaign's card the
#: instant they finish the first one — which is how a feedback system turns into popups. It
#: also covers re-presenting one unanswered offer: that waits for a later visit rather than
#: the next route change.
SHOW_COOLDOWN = timedelta(hours=12)

#: How long a negative eligibility result is remembered per user. The pending endpoint is
#: polled on every route change, so without this a user who matches nothing would re-run the
#: audience and activity checks all day. Best-effort only: the cache is per-process when Redis
#: is not configured, which costs a few extra queries rather than correctness.
_INELIGIBLE_TTL = 600


def _ineligible_cache_key(user_id: int, campaign_id: int) -> str:
    return f"surveys:ineligible:{user_id}:{campaign_id}"


def get_campaign(slug: str) -> SurveyCampaign | None:
    return SurveyCampaign.objects.filter(slug=slug).first()


def live_campaigns(trigger: str | None = None) -> list[SurveyCampaign]:
    """Campaigns that are active and inside their window, optionally filtered by trigger.

    Deliberately uncached: it is one indexed query returning a handful of rows, and a campaign
    activated in admin should take effect immediately. The expensive part of eligibility is the
    per-user audience and activity check, which is what the negative cache below covers.
    """
    now = timezone.now()
    campaigns = SurveyCampaign.objects.filter(active=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gte=now),
    )
    if trigger:
        campaigns = campaigns.filter(trigger=trigger)
    return list(campaigns)


def qualifying_sessions(user):
    """Finished standard calls where both users were active and which ran under ten minutes.

    Random calls are excluded — the same rule as the post-call offer trigger.
    """
    from video.models import LivekitSession

    return (
        LivekitSession.objects.filter(
            Q(u1=user) | Q(u2=user),
            both_have_been_active=True,
            end_time__isnull=False,
            random_call_session=False,
        )
        .annotate(duration=ExpressionWrapper(F("end_time") - F("created_at"), output_field=DurationField()))
        .filter(duration__lt=QUALIFYING_CALL_MAX_DURATION)
    )


def first_qualifying_call_at(user):
    return qualifying_sessions(user).order_by("end_time").values_list("end_time", flat=True).first()


def onboarded_at(user):
    """When the user finished onboarding — same sources as match-proposal stats.

    ``is_onboarded`` can be true without a timestamp (legacy). Callers that need a date
    treat that as unknown rather than inventing one.
    """
    state = getattr(user, "state", None)
    if state is None or not state.is_onboarded:
        return None
    candidates = []
    if state.onboarding_call_completed_at:
        candidates.append(state.onboarding_call_completed_at)
    if state.self_onboarding_completed_at:
        day = datetime.combine(state.self_onboarding_completed_at, time.min)
        candidates.append(timezone.make_aware(day) if timezone.is_naive(day) else day)
    if candidates:
        return min(candidates)
    from management.models.pre_matching_appointment import PreMatchingAppointment

    earliest = PreMatchingAppointment.objects.filter(user=user, end_time__isnull=False).order_by("end_time").first()
    return earliest.end_time if earliest else None


def _matches_for_user(user, *, active_only: bool = False):
    """Real tandem matches — not the support chat every user is paired with at signup."""
    from management.models.matches import Match
    from management.models.unconfirmed_matches import MatchType

    qs = Match.objects.filter(Q(user1=user) | Q(user2=user), support_matching=False).exclude(
        match_type=MatchType.TEMPORARY
    )
    if active_only:
        qs = qs.filter(active=True)
    return qs


def _match_success_at(match):
    """When this match first counted as successful under the active definition."""
    from management.match_success.sessions import qualifying_sessions as match_sessions
    from management.match_success.versions.v1_total_minutes import SUCCESS_MINUTES

    times = []
    if match.completed_off_plattform:
        times.append(match.completed_off_plattform_auto_marked_at or match.updated_at)
    total = timedelta(0)
    threshold = timedelta(minutes=SUCCESS_MINUTES)
    for session in match_sessions(match).order_by("end_time"):
        total += session.end_time - session.created_at
        if total >= threshold:
            times.append(session.end_time)
            break
    return min(times) if times else None


def user_has_successful_match(user) -> bool:
    """True if *any* of the user's tandem matches count as successful.

    Match-based eligibility is user-scoped: a second successful match does not produce a
    second offer. Once-per-match offering would need ``repeat_scope=context`` and
    ``context_type=match``, which pending delivery does not iterate yet.
    """
    from management.match_success import successful_matches

    return successful_matches(_matches_for_user(user)).exists()


def _eligible_event_at(event: str, user):
    """When the named condition first became true for this user, or ``None``."""
    from management.match_success import successful_matches

    if event == SurveyCampaign.EligibleAfterEvent.ONBOARDED:
        return onboarded_at(user)
    if event == SurveyCampaign.EligibleAfterEvent.FIRST_QUALIFYING_CALL:
        return first_qualifying_call_at(user)
    if event == SurveyCampaign.EligibleAfterEvent.MATCH_CREATED:
        return (
            _matches_for_user(user, active_only=True)
            .order_by("created_at")
            .values_list("created_at", flat=True)
            .first()
        )
    if event == SurveyCampaign.EligibleAfterEvent.MATCH_SUCCESS:
        times = [_match_success_at(match) for match in successful_matches(_matches_for_user(user))]
        dated = [moment for moment in times if moment is not None]
        return min(dated) if dated else None
    return None


def user_is_eligible(campaign: SurveyCampaign, user) -> bool:
    """Audience and named journey condition — repeat rules are handled per context key.

    Conditions take effect as soon as they are true. Match created / match success qualify
    if *any* tandem match satisfies the rule. ``eligible_after_since`` is a lower bound on
    when that condition counted: older events do not qualify.
    """
    if not user_matches_audience(campaign, user):
        return False
    event = campaign.eligible_after_event
    if not event:
        return True
    since = campaign.eligible_after_since
    if event == SurveyCampaign.EligibleAfterEvent.MATCH_CREATED:
        qs = _matches_for_user(user, active_only=True)
        if since:
            qs = qs.filter(created_at__gte=since)
        return qs.exists()
    if event == SurveyCampaign.EligibleAfterEvent.MATCH_SUCCESS:
        from management.match_success import successful_matches

        matches = successful_matches(_matches_for_user(user))
        if not since:
            return matches.exists()
        return any((moment := _match_success_at(match)) is not None and moment >= since for match in matches)

    happened_at = _eligible_event_at(event, user)
    if happened_at is None:
        # Legacy onboarded users have the flag but no timestamp — include them only when
        # there is no lower bound to check.
        if (
            event == SurveyCampaign.EligibleAfterEvent.ONBOARDED
            and not since
            and bool(getattr(getattr(user, "state", None), "is_onboarded", False))
        ):
            return True
        return False
    if since and happened_at < since:
        return False
    return timezone.now() >= happened_at


#: ``none`` is already "Everyone" on the audience picker.
_HIDDEN_AUDIENCE_FILTERS = {CustomFilterChoices.NONE}

AUDIENCE_FILTER_LABELS = {
    CustomFilterChoices.LEARNERS_WITH_A1A2: "Learners with A1/A2 German",
    CustomFilterChoices.LEARNERS_ABOVE_A1A2: "Learners above A1/A2",
    CustomFilterChoices.VOLUNTEERS: "Volunteers",
    CustomFilterChoices.LEARNERS: "Learners",
    CustomFilterChoices.LEARNERS_OUTSIDE_GERMANY: "Learners outside Germany",
    CustomFilterChoices.RANDOM_CALL_USERS: "Random-call users",
    CustomFilterChoices.MATCH_ELIGIBLE_USERS: "Match-eligible users",
    CustomFilterChoices.NRW_RESIDENTS: "NRW residents",
}


def company_audience_values() -> list[str]:
    """Distinct companies currently on user accounts, for the audience picker."""
    from management.models.state import State

    return list(
        State.objects.exclude(company__isnull=True)
        .exclude(company="")
        .values_list("company", flat=True)
        .distinct()
        .order_by("company")
    )


def audience_filter_choices() -> list[dict[str, str]]:
    return [
        {"value": value, "label": AUDIENCE_FILTER_LABELS.get(value, value)}
        for value in CustomFilterChoices.values
        if value not in _HIDDEN_AUDIENCE_FILTERS
    ]


def audience_label(campaign: SurveyCampaign) -> str:
    if campaign.audience_type == SurveyCampaign.AudienceType.COMPANY:
        return campaign.audience_value or "Company"
    if campaign.audience_type == SurveyCampaign.AudienceType.FILTER:
        return AUDIENCE_FILTER_LABELS.get(campaign.audience_value, campaign.audience_value)
    return "Everyone"


def user_matches_audience(campaign: SurveyCampaign, user) -> bool:
    if campaign.audience_type == SurveyCampaign.AudienceType.ALL:
        return True
    if campaign.audience_type == SurveyCampaign.AudienceType.COMPANY:
        company = getattr(getattr(user, "state", None), "company", None)
        return bool(company) and company.strip().lower() == campaign.audience_value.strip().lower()
    if campaign.audience_type == SurveyCampaign.AudienceType.FILTER:
        match = FILTER_FUNC_MAP.get(campaign.audience_value)
        return bool(match and match(user))
    return False


def offer_survey(campaign: SurveyCampaign, user, *, context_key: str = "", live_session=None) -> SurveyResponse | None:
    """Create the offer for ``(campaign, user, context_key)``, or return the open one.

    Returns ``None`` when the user has already answered or dismissed this survey, which is
    what makes the uniqueness rule the single source of truth for "ask again or not".
    """
    if campaign.is_context_scoped and not context_key:
        raise ValueError(f"Campaign '{campaign.slug}' is context-scoped and needs a context_key")
    if not campaign.is_context_scoped and context_key:
        raise ValueError(f"Campaign '{campaign.slug}' is user-scoped and cannot take a context_key")

    try:
        with transaction.atomic():
            response, created = SurveyResponse.objects.get_or_create(
                campaign=campaign,
                user=user,
                context_key=context_key,
                defaults={"live_session": live_session},
            )
    except IntegrityError:
        # Lost a race against a concurrent poll; the winner's row is the offer.
        response, created = SurveyResponse.objects.get(campaign=campaign, user=user, context_key=context_key), False

    if not created and response.is_terminal:
        return None
    return response


def _post_call_context_key(campaign: SurveyCampaign, live_session) -> str:
    """Context key for a review the legacy endpoint is about to record.

    The old endpoint accepted a review with no live session at all, and there is no context
    to key such a row on. Rather than drop the feedback or collapse every session-less review
    of one user onto a single row, each gets its own ``legacy:<uuid>`` key: the uniqueness
    rule stays intact and the key says plainly where the row came from.
    """
    if not campaign.is_context_scoped:
        return ""
    if live_session is not None:
        return build_context_key(SurveyCampaign.ContextType.LIVE_SESSION, live_session.uuid)
    return build_context_key("legacy", uuid4())


def offer_post_call_survey(user, live_session) -> SurveyResponse | None:
    """Offer every live after-a-call campaign to one participant of a finished standard call.

    Every campaign with the ``event:call_ended`` trigger is offered, not just ``post-call``:
    the admin panel lets any campaign choose that trigger, and a campaign that quietly
    collects nothing is the failure this feature exists to remove. A context-scoped campaign
    is keyed on the session, a user-scoped one is asked once ever.

    Random calls (``LivekitSession.random_call_session``) are excluded — that flow has its
    own post-call UX and should not surface the standard call survey. Calls that ran ten
    minutes or longer are excluded too.

    Returns the first offer made, which is the whole result while ``post-call`` is the only
    campaign using this trigger.
    """
    if getattr(live_session, "random_call_session", False):
        return None
    if live_session.end_time is None:
        return None
    if live_session.end_time - live_session.created_at >= QUALIFYING_CALL_MAX_DURATION:
        return None

    first = None
    for campaign in live_campaigns(SurveyCampaign.Trigger.CALL_ENDED):
        if not user_is_eligible(campaign, user):
            continue
        response = offer_survey(
            campaign,
            user,
            context_key=_post_call_context_key(campaign, live_session),
            live_session=live_session,
        )
        if response is not None and first is None:
            first = response
    return first


def last_shown_at(user):
    """When this user was last shown any survey card, or ``None``.

    ``shown_at`` is only written when the client confirms it rendered the card, so a survey
    that was offered but never displayed does not start the quiet period.
    """
    return SurveyResponse.objects.filter(user=user, shown_at__isnull=False).aggregate(latest=Max("shown_at"))["latest"]


def _in_cooldown(user, now) -> bool:
    last_shown = last_shown_at(user)
    return last_shown is not None and now - last_shown < SHOW_COOLDOWN


def _deliverable(response: SurveyResponse, campaign: SurveyCampaign) -> bool:
    """Whether this offer is still worth presenting, ignoring timing.

    The cooldown is not checked here: it is a property of the user, not of one offer, and is
    applied once in ``pending_survey_for_user``.
    """
    if response.is_terminal:
        return False
    if response.shown_count >= campaign.max_shows:
        response.expire()
        return False
    return True


def pending_survey_for_user(user) -> SurveyResponse | None:
    """The survey this user should see right now, if any.

    At most one card per ``SHOW_COOLDOWN``, whichever campaign it belongs to. Open offers
    created by an event trigger come first; only then are ``on_session`` campaigns evaluated,
    so the common case is one indexed query.

    A user inside the quiet period is offered nothing and *creates* nothing: the rows an event
    trigger already wrote stay open and are delivered once the window passes, so deferring a
    survey never loses it.
    """
    now = timezone.now()
    if _in_cooldown(user, now):
        return None

    campaigns_by_id = {campaign.pk: campaign for campaign in live_campaigns()}
    if not campaigns_by_id:
        return None

    open_offers = SurveyResponse.objects.filter(
        user=user,
        campaign_id__in=campaigns_by_id,
        status=SurveyResponse.Status.SHOWN,
    ).order_by("-created_at")
    for response in open_offers:
        campaign = campaigns_by_id[response.campaign_id]
        if _deliverable(response, campaign):
            response.campaign = campaign
            return response

    for campaign in campaigns_by_id.values():
        if campaign.trigger != SurveyCampaign.Trigger.ON_SESSION:
            continue
        # There is no context to key an offer on here. `SurveyCampaign.clean` refuses this
        # combination, so reaching it means a row predates that rule or was written around
        # the model — skip it rather than let one campaign 500 the endpoint for everyone.
        if campaign.is_context_scoped:
            continue
        cache_key = _ineligible_cache_key(user.pk, campaign.pk)
        if cache.get(cache_key):
            continue
        if not user_is_eligible(campaign, user):
            cache.set(cache_key, True, _INELIGIBLE_TTL)
            continue
        response = offer_survey(campaign, user)
        if response is not None and _deliverable(response, campaign):
            response.campaign = campaign
            return response
    return None


def validate_answers(campaign: SurveyCampaign, answers) -> dict:
    """Check submitted answers against the campaign's declared questions.

    Unknown keys are rejected rather than stored: ``answers`` is the permanent record that
    question immutability protects, so anything in it has to correspond to a question.
    """
    if not isinstance(answers, dict):
        raise ValidationError("answers must be an object.")

    known_ids = {question["id"] for question in campaign.questions}
    unknown = set(answers) - known_ids
    if unknown:
        raise ValidationError(f"Unknown answer keys: {sorted(unknown)}.")

    cleaned: dict = {}
    for question in campaign.questions:
        qid, qtype = question["id"], question["type"]
        value = answers.get(qid)
        is_blank = value is None or (isinstance(value, str) and not value.strip())

        if is_blank:
            if question.get("required"):
                raise ValidationError(f"'{qid}' is required.")
            continue

        if qtype == QuestionType.RATING:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError(f"'{qid}' must be a whole number.")
            if not 1 <= value <= campaign.scale:
                raise ValidationError(f"'{qid}' must be between 1 and {campaign.scale}.")
            cleaned[qid] = value
        elif qtype == QuestionType.TEXT:
            if not isinstance(value, str):
                raise ValidationError(f"'{qid}' must be text.")
            text = value.strip()
            if len(text) > MAX_TEXT_ANSWER_LENGTH:
                raise ValidationError(f"'{qid}' is longer than {MAX_TEXT_ANSWER_LENGTH} characters.")
            cleaned[qid] = text
        elif qtype == QuestionType.CHOICE:
            if value not in option_values(question):
                raise ValidationError(f"'{value}' is not an option of '{qid}'.")
            cleaned[qid] = value

    return cleaned


def submit_survey(response: SurveyResponse, answers, *, allow_resubmit: bool = False) -> SurveyResponse:
    if response.is_terminal and not allow_resubmit:
        raise ValidationError("This survey has already been answered.")
    response.submit(validate_answers(response.campaign, answers))
    return response


def submit_post_call_review(user, *, live_session, rating, review, response_id=None) -> SurveyResponse:
    """Back-compatible entry point for ``POST /api/livekit/review``.

    Exists only while older clients are still in the wild; they post a rating against a live
    session rather than against a survey id. Resolving that to the right offer belongs here
    with the rest of the survey rules, not in the video app.
    """
    campaign = get_campaign(POST_CALL_SLUG)
    if campaign is None:
        raise ValidationError("The post-call survey campaign does not exist.")

    answers = {"rating": rating, "comment": review}

    if response_id is not None:
        # Scoped to the post-call campaign on purpose. ``review_id`` is client-supplied, and
        # before the migration it was a PostCallReview pk — unrelated to SurveyResponse pks —
        # so an id that lands on another campaign's row is stale or crafted either way. Fall
        # through to session resolution rather than write a call rating over an unrelated
        # survey's answers.
        response = (
            SurveyResponse.objects.filter(pk=response_id, user=user, campaign=campaign)
            .select_related("campaign")
            .first()
        )
        if response is not None:
            # The old endpoint let a client overwrite its own review, so the shim keeps that.
            return submit_survey(response, answers, allow_resubmit=True)

    open_offers = SurveyResponse.objects.filter(
        campaign=campaign, user=user, status=SurveyResponse.Status.SHOWN
    ).order_by("-created_at")
    response = (
        open_offers.filter(live_session=live_session).first() if live_session is not None else open_offers.first()
    )

    if response is None:
        # Nothing open to answer, so this would be a brand new offer. A retired campaign
        # should not gain those; while it is live the old endpoint's promise holds and the
        # feedback is recorded rather than rejected.
        if not campaign.is_live():
            raise ValidationError("The post-call survey is no longer active.")
        response = offer_survey(
            campaign,
            user,
            context_key=_post_call_context_key(campaign, live_session),
            live_session=live_session,
        )

    if response is None:
        raise ValidationError("This call has already been reviewed.")
    response.campaign = campaign
    return submit_survey(response, answers)


def dismiss_survey(response: SurveyResponse) -> SurveyResponse:
    """Record a close-without-answering. Terminal, and distinct from never being shown."""
    if not response.is_terminal:
        response.dismiss()
    return response
