"""Offering, answering and expiring in-app surveys.

Eligibility is evaluated when the user is actually in the app, never precomputed into a
frozen cohort: a user who gains the company field next week is included automatically, and a
user who never returns leaves no row behind.

Popup delivery is the polled pending endpoint. WebSocket-only delivery is what failed
silently for a year, so the ``event:call_ended`` trigger *creates* an offer and the next
poll finds it — which also removes the "only if the user is connected" limitation.

Link delivery is a second channel: ``GET /api/surveys/<slug>`` for campaigns with
``available_via_link``. It shares the same uniqueness rule and answer record, but ignores
cooldown and max_shows, does not write ``shown_at``, and does not appear in the popup queue.
"""

import logging
from datetime import datetime, time, timedelta
from uuid import UUID

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import DurationField, ExpressionWrapper, F, Max, Q
from django.utils import timezone

from management.models.audience_filters import FILTER_FUNC_MAP, AudienceFilters
from management.models.survey import (
    MAX_TEXT_ANSWER_LENGTH,
    PRIMARY_COPY_LANGUAGE,
    QUALIFYING_CALL_MIN_DURATION,
    QuestionType,
    SurveyCampaign,
    SurveyResponse,
    build_context_key,
    option_values,
    option_values_in_order,
    rating_scale_for,
    resolve_localized,
)

logger = logging.getLogger(__name__)

POST_CALL_SLUG = "post-call"

#: Quiet period after a user is shown any survey card, across every campaign.
#:
#: Deliberately user-wide rather than per offer. The client refetches the pending endpoint as
#: soon as a survey closes, so a per-offer rule hands the user the next campaign's card the
#: instant they finish the first one — which is how a feedback system turns into popups. It
#: also covers re-presenting one unanswered offer: that waits for a later visit rather than
#: the next route change.
SHOW_COOLDOWN = timedelta(hours=12)


class SurveyLinkState:
    """Outcomes of ``survey_for_link``. ``not_found`` is the 404 bucket: unknown slug,
    ``available_via_link=False``, match-scoped (unsupported), or a ``live_session`` that
    does not exist, is still in progress, or does not belong to the user. Those last
    cases are indistinguishable on purpose so the endpoint cannot leak whether a uuid
    is real.
    """

    NOT_FOUND = "not_found"
    AVAILABLE = "available"
    ALREADY_SUBMITTED = "already_submitted"
    UNAVAILABLE = "unavailable"
    INELIGIBLE = "ineligible"
    INACTIVE = "inactive"
    MISSING_CONTEXT = "missing_context"


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
    """Finished standard calls where both users were active and which ran long enough to count.

    "Qualifying" is one threshold with one meaning — a call long enough to be a real
    conversation. It answers "has this user actually had a call yet", so a longer call counts
    for more, never less.

    Random calls are excluded, the same as for the post-call trigger.
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
        .filter(duration__gte=QUALIFYING_CALL_MIN_DURATION)
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


def _match_halfway_at(match):
    """When this match first reached half the live match-success token threshold."""
    from management.match_success import halfway_token_threshold, tokens_from_total_minutes
    from management.match_success.sessions import qualifying_sessions as match_sessions

    half = halfway_token_threshold()
    times = []
    if match.completed_off_plattform:
        times.append(match.completed_off_plattform_auto_marked_at or match.updated_at)
    total = timedelta(0)
    for session in match_sessions(match).order_by("end_time"):
        total += session.end_time - session.created_at
        if tokens_from_total_minutes(total.total_seconds() / 60) >= half:
            times.append(session.end_time)
            break
    return min(times) if times else None


def _user_has_halfway_match(user) -> bool:
    """True if *any* tandem match has reached half the live success token target."""
    from management.match_success import halfway_token_threshold, match_tokens_by_id

    matches = _matches_for_user(user)
    if matches.filter(completed_off_plattform=True).exists():
        return True
    half = halfway_token_threshold()
    return any(count >= half for count in match_tokens_by_id(matches).values())


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
    if event == SurveyCampaign.EligibleAfterEvent.HALFWAY_MATCH_SUCCESS:
        times = [_match_halfway_at(match) for match in _matches_for_user(user)]
        dated = [moment for moment in times if moment is not None]
        return min(dated) if dated else None
    return None


def user_is_eligible(campaign: SurveyCampaign, user) -> bool:
    """Audience and named journey condition — repeat rules are handled per context key.

    Conditions take effect as soon as they are true. Match created / halfway to match
    success / match success qualify if *any* tandem match satisfies the rule.
    ``eligible_after_since`` is a lower bound on when that condition counted: older
    events do not qualify.
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
    if event == SurveyCampaign.EligibleAfterEvent.HALFWAY_MATCH_SUCCESS:
        if not since:
            return _user_has_halfway_match(user)
        return any(
            (moment := _match_halfway_at(match)) is not None and moment >= since for match in _matches_for_user(user)
        )

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
_HIDDEN_AUDIENCE_FILTERS = {AudienceFilters.NONE}


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
        {"value": str(value), "label": str(value.label)}
        for value in AudienceFilters
        if value not in _HIDDEN_AUDIENCE_FILTERS
    ]


def audience_label(campaign: SurveyCampaign) -> str:
    if campaign.audience_type == SurveyCampaign.AudienceType.COMPANY:
        return campaign.audience_value or "Company"
    if campaign.audience_type == SurveyCampaign.AudienceType.FILTER:
        try:
            return str(AudienceFilters(campaign.audience_value).label)
        except ValueError:
            return campaign.audience_value
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


def _notify_survey_offered(user) -> None:
    """Nudge a connected client to re-fetch the pending endpoint.

    Best effort, and deliberately after the row exists: the socket only saves the user a
    wait, it is never how the survey arrives. A push that fails costs nothing because the
    next poll still finds the row — which is the whole reason delivery moved off the socket.
    """
    from chat.consumers.messages import SurveyOffered

    try:
        SurveyOffered().send(str(user.uuid))
    except Exception:
        logger.warning("Could not push survey_offered to user %s", user.pk, exc_info=True)


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
    if created:
        _notify_survey_offered(user)
    return response


def _post_call_context_key(campaign: SurveyCampaign, live_session) -> str:
    """Context key for an offer made after a call.

    A user-scoped campaign takes an empty key — it is asked once ever, not once per call.
    """
    if not campaign.is_context_scoped:
        return ""
    return build_context_key(SurveyCampaign.ContextType.LIVE_SESSION, live_session.uuid)


def offer_post_call_survey(user, live_session) -> SurveyResponse | None:
    """Offer the campaigns that match how this call went, to one participant of it.

    Which trigger fires depends on the call's length, split at ``QUALIFYING_CALL_MIN_DURATION``:
    a call that ran long enough is a real conversation and fires ``QUALIFYING_CALL_ENDED``; a
    shorter one fires ``NON_QUALIFYING_CALL_ENDED``, which is there to find out what went wrong.

    Every live campaign on the matching trigger is offered, not just ``post-call``: the admin
    panel lets any campaign choose one, and a campaign that quietly collects nothing is the
    failure this feature exists to remove. A context-scoped campaign is keyed on the session, a
    user-scoped one is asked once ever.

    Random calls (``LivekitSession.random_call_session``) are excluded — that flow has its
    own post-call UX and should not surface the standard call survey.

    Returns the first offer made — the whole result while each trigger has at most one
    campaign on it.
    """
    if getattr(live_session, "random_call_session", False):
        return None
    if live_session.end_time is None:
        return None

    # The call's length picks the trigger, so every finished standard call reaches exactly one
    # of the two: a real conversation gets asked how it went, a short one gets asked what went
    # wrong. A campaign on the other trigger simply is not selected here.
    duration = live_session.end_time - live_session.created_at
    trigger = (
        SurveyCampaign.Trigger.QUALIFYING_CALL_ENDED
        if duration >= QUALIFYING_CALL_MIN_DURATION
        else SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED
    )

    first = None
    for campaign in live_campaigns(trigger):
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

    open_offers = (
        SurveyResponse.objects.filter(
            user=user,
            campaign_id__in=campaigns_by_id,
            status=SurveyResponse.Status.SHOWN,
        )
        .exclude(delivery_channel=SurveyResponse.DeliveryChannel.LINK)
        .order_by("-created_at")
    )
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
        # Uniqueness may return a row the link channel already created. That slot is
        # consumed, but it must not surface as a popup.
        if response is None or response.delivery_channel == SurveyResponse.DeliveryChannel.LINK:
            continue
        if _deliverable(response, campaign):
            response.campaign = campaign
            return response
    return None


def _finished_session_owned_by(user, live_session_id):
    """A finished call this user was in, or ``None``.

    ``None`` covers a missing/malformed uuid, a session that is not theirs, one that
    does not exist, and one that has not ended yet. Callers must treat all of those as
    ``not_found`` — do not distinguish "yours but still running" from "someone else's".
    """
    from video.models import LivekitSession

    if not live_session_id:
        return None
    try:
        session_uuid = UUID(str(live_session_id))
    except (ValueError, TypeError, AttributeError):
        return None
    return (
        LivekitSession.objects.filter(uuid=session_uuid, end_time__isnull=False).filter(Q(u1=user) | Q(u2=user)).first()
    )


def _mark_link_opened(response: SurveyResponse) -> None:
    if response.opened_at is not None:
        return
    response.opened_at = timezone.now()
    response.save(update_fields=["opened_at", "updated_at"])


def _offer_for_link(campaign: SurveyCampaign, user, *, context_key: str = "", live_session=None) -> SurveyResponse:
    """get_or_create the unique row for this link visit, without notifying the popup path."""
    try:
        with transaction.atomic():
            response, _created = SurveyResponse.objects.get_or_create(
                campaign=campaign,
                user=user,
                context_key=context_key,
                defaults={
                    "live_session": live_session,
                    "delivery_channel": SurveyResponse.DeliveryChannel.LINK,
                },
            )
    except IntegrityError:
        response = SurveyResponse.objects.get(campaign=campaign, user=user, context_key=context_key)
    return response


def survey_for_link(user, slug: str, *, live_session_id=None) -> tuple[str, SurveyResponse | None]:
    """Resolve a campaign URL for this user.

    Returns ``(state, response)``. ``response`` is only set for ``available`` (the card
    to render) and is ``None`` otherwise. ``not_found`` means the API should 404 with a
    generic body.

    A ``?match=`` query param is out of scope for v1 and must not be passed here.
    """
    campaign = get_campaign(slug)
    if campaign is None or not campaign.available_via_link:
        return SurveyLinkState.NOT_FOUND, None
    # Match-scoped campaigns are rejected in ``clean()``. A row written around the
    # model still has no resolver, so treat it as missing rather than 500.
    if campaign.context_type == SurveyCampaign.ContextType.MATCH:
        return SurveyLinkState.NOT_FOUND, None

    live_session = None
    context_key = ""
    if campaign.is_context_scoped:
        if campaign.context_type != SurveyCampaign.ContextType.LIVE_SESSION:
            return SurveyLinkState.NOT_FOUND, None
        if not live_session_id:
            return SurveyLinkState.MISSING_CONTEXT, None
        live_session = _finished_session_owned_by(user, live_session_id)
        if live_session is None:
            return SurveyLinkState.NOT_FOUND, None
        context_key = build_context_key(SurveyCampaign.ContextType.LIVE_SESSION, live_session.uuid)

    existing = (
        SurveyResponse.objects.select_related("campaign")
        .filter(campaign=campaign, user=user, context_key=context_key)
        .first()
    )
    if existing is not None and existing.status == SurveyResponse.Status.SUBMITTED:
        return SurveyLinkState.ALREADY_SUBMITTED, None

    if not campaign.is_live():
        return SurveyLinkState.INACTIVE, None
    if existing is not None and existing.status == SurveyResponse.Status.EXPIRED:
        return SurveyLinkState.UNAVAILABLE, None
    if not user_is_eligible(campaign, user):
        return SurveyLinkState.INELIGIBLE, None

    response = existing or _offer_for_link(campaign, user, context_key=context_key, live_session=live_session)
    response.campaign = campaign
    _mark_link_opened(response)
    return SurveyLinkState.AVAILABLE, response


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
        is_blank = (
            value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, list) and not value)
        )

        if is_blank:
            if question.get("required"):
                raise ValidationError(f"'{qid}' is required.")
            continue

        if qtype == QuestionType.RATING:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError(f"'{qid}' must be a whole number.")
            scale = rating_scale_for(question, campaign)
            if not 1 <= value <= scale:
                raise ValidationError(f"'{qid}' must be between 1 and {scale}.")
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
        elif qtype == QuestionType.MULTISELECT:
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValidationError(f"'{qid}' must be a list of option values.")
            allowed = option_values(question)
            unknown_options = [item for item in value if item not in allowed]
            if unknown_options:
                raise ValidationError(f"{unknown_options} are not options of '{qid}'.")
            # Store in the question's option order, unique. Click order is not part of the answer.
            selected = set(value)
            cleaned[qid] = [item for item in option_values_in_order(question) if item in selected]

    return cleaned


def submit_survey(response: SurveyResponse, answers, *, allow_resubmit: bool = False) -> SurveyResponse:
    # ``blocks_link`` rather than ``is_terminal``: a dismissed popup must still be
    # answerable at the campaign URL. ``allow_resubmit`` remains the escape hatch for
    # SUBMITTED / EXPIRED; nothing in-tree currently passes it.
    if response.blocks_link and not allow_resubmit:
        raise ValidationError("This survey has already been answered.")
    response.submit(validate_answers(response.campaign, answers))
    return response


def dismiss_survey(response: SurveyResponse) -> SurveyResponse:
    """Record a close-without-answering. Terminal, and distinct from never being shown."""
    if not response.is_terminal:
        response.dismiss()
    return response


def campaign_response_summary(campaign: SurveyCampaign) -> dict:
    """Per-question rating means for one campaign, from submitted answers JSON.

    A single campaign-level average is not meaningful once a survey can have several ratings
    on different scales. Computed here rather than annotated on every campaign list row.
    """
    responses = SurveyResponse.objects.filter(campaign=campaign)
    submitted_answers = list(responses.filter(status=SurveyResponse.Status.SUBMITTED).values_list("answers", flat=True))
    rating_means = []
    for question in campaign.questions:
        if question.get("type") != QuestionType.RATING:
            continue
        qid = question.get("id")
        if not qid:
            continue
        scores = [
            value
            for answers in submitted_answers
            if isinstance(answers, dict)
            for value in [answers.get(qid)]
            if isinstance(value, int) and not isinstance(value, bool)
        ]
        rating_means.append(
            {
                "id": qid,
                "label": resolve_localized(question.get("label"), PRIMARY_COPY_LANGUAGE) or qid,
                "scale": rating_scale_for(question, campaign),
                "mean": round(sum(scores) / len(scores), 2) if scores else None,
                "n": len(scores),
            }
        )
    return {
        "offered": responses.count(),
        "answered": len(submitted_answers),
        "rating_means": rating_means,
    }
