"""User-facing survey endpoints.

``pending`` is popup delivery. It works for offline users, works for native via the same
JWT auth as every other endpoint, and fails loudly — a survey that stops appearing is a
request returning nothing rather than silence.

``GET /api/surveys/<slug>`` is the link channel for campaigns with ``available_via_link``.
Submit still goes through ``/api/surveys/<id>/submit``. The page must not call ``shown``
or ``dismiss``.

``shown`` is separate from ``pending`` on purpose: the pending response proves the
*backend* offered the survey, while ``shown`` proves the client actually rendered it.
Offers piling up with ``shown_count`` stuck at zero is precisely the failure that went
unnoticed for a year.
"""

import logging

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from management import surveys
from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.helpers.detailed_pagination import get_paginated_format_v2
from management.models.survey import (
    PRIMARY_COPY_LANGUAGE,
    QuestionType,
    SurveyCampaign,
    SurveyResponse,
    rating_scale_for,
)

logger = logging.getLogger(__name__)


class PendingSurveySerializer(serializers.Serializer):
    """Everything the client needs to render the card, as finished text.

    Copy is resolved to the user's language here rather than sent as a language map, so the
    renderer has no language logic and no way to show the wrong one.
    """

    id = serializers.IntegerField()
    campaign = serializers.CharField()
    scale = serializers.IntegerField()
    context_key = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    submit_button = serializers.CharField()
    questions = serializers.JSONField()

    # The fields above document the payload; the values come from the campaign's copy rather
    # than from attributes of the response, so they are assembled rather than read.
    def to_representation(self, response):
        campaign = response.campaign
        return {
            "id": response.pk,
            "campaign": campaign.slug,
            "scale": campaign.scale,
            "context_key": response.context_key,
            **campaign.card_for(self.context["language"]),
        }


def _display_language(user) -> str:
    return getattr(getattr(user, "profile", None), "display_language", "") or PRIMARY_COPY_LANGUAGE


class SubmitSurveySerializer(serializers.Serializer):
    answers = serializers.JSONField()


def _get_own_response(request, response_id: int) -> SurveyResponse | None:
    return SurveyResponse.objects.select_related("campaign").filter(pk=response_id, user=request.user).first()


@extend_schema(
    description="The survey the current user should be shown, or null.",
    responses={200: PendingSurveySerializer(many=False)},
)
@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def pending_survey(request):
    response = surveys.pending_survey_for_user(request.user)
    if response is None:
        return Response({"survey": None})
    payload = PendingSurveySerializer(response, context={"language": _display_language(request.user)}).data
    return Response({"survey": payload})


@extend_schema(description="Confirm the client rendered the survey card.", responses={200: {"status": "ok"}})
@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_survey_shown(request, response_id: int):
    response = _get_own_response(request, response_id)
    if response is None:
        return Response({"status": "error", "message": "Survey not found"}, status=404)
    if not response.is_terminal:
        response.mark_shown()
    return Response({"status": "ok", "shown_count": response.shown_count})


@extend_schema(
    request=SubmitSurveySerializer(many=False),
    responses={200: {"status": "ok"}},
)
@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def submit_survey(request, response_id: int):
    response = _get_own_response(request, response_id)
    if response is None:
        return Response({"status": "error", "message": "Survey not found"}, status=404)

    serializer = SubmitSurveySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        surveys.submit_survey(response, serializer.validated_data["answers"])
    except ValidationError as e:
        # The message stays generic. Validation text here reflects the caller's own payload
        # back at them ("'x' is not an option of 'y'") and describes internal structure, so
        # it belongs in the log, not the response. The client already validates required
        # answers before submitting, so a failure here is a crafted or out-of-date request.
        logger.warning(
            "Rejected survey submission for response %s (user %s): %s",
            response.pk,
            request.user.pk,
            "; ".join(e.messages),
        )
        return Response({"status": "error", "message": "Invalid survey answers"}, status=400)
    return Response({"status": "ok", "survey_id": response.pk})


@extend_schema(
    description="Record that the user closed the survey without answering.",
    responses={200: {"status": "ok"}},
)
@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def dismiss_survey(request, response_id: int):
    response = _get_own_response(request, response_id)
    if response is None:
        return Response({"status": "error", "message": "Survey not found"}, status=404)
    surveys.dismiss_survey(response)
    return Response({"status": "ok"})


@extend_schema(
    description=(
        "The survey at this campaign slug for the current user. "
        "Optional ?live_session=<uuid> for live-session-scoped campaigns. "
        "Unknown slugs, campaigns that are not available_via_link, and live_session "
        "values that are missing, unfinished, or not the user's all 404."
    ),
    responses={200: PendingSurveySerializer(many=False)},
)
@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def survey_by_slug(request, slug: str):
    state, response = surveys.survey_for_link(
        request.user,
        slug,
        live_session_id=request.query_params.get("live_session") or None,
    )
    if state == surveys.SurveyLinkState.NOT_FOUND:
        return Response({"status": "error", "message": "Survey not found"}, status=404)
    survey_payload = None
    if state == surveys.SurveyLinkState.AVAILABLE and response is not None:
        survey_payload = PendingSurveySerializer(response, context={"language": _display_language(request.user)}).data
    return Response({"state": state, "survey": survey_payload})


#: ---------------------------------------------------------------------------------------
#: Admin panel: campaigns are created and edited here rather than in code, which is why the
#: copy lives on the row. Validation is the model's — these views only translate its errors.
#: ---------------------------------------------------------------------------------------


class AdminSurveyCampaignSerializer(serializers.ModelSerializer):
    offered = serializers.IntegerField(read_only=True, default=0)
    answered = serializers.IntegerField(read_only=True, default=0)
    rendered = serializers.IntegerField(read_only=True, default=0)
    missing_copy = serializers.SerializerMethodField()
    audience_label = serializers.SerializerMethodField()

    class Meta:
        model = SurveyCampaign
        fields = (
            "id",
            "slug",
            "name",
            "copy",
            "scale",
            "questions",
            "audience_type",
            "audience_value",
            "audience_label",
            "trigger",
            "eligible_after_event",
            "eligible_after_since",
            "repeat_scope",
            "context_type",
            "active",
            "starts_at",
            "ends_at",
            "max_shows",
            "available_via_link",
            "created_at",
            "updated_at",
            "offered",
            "answered",
            "rendered",
            "missing_copy",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_missing_copy(self, campaign) -> list[str]:
        """What blocks activation, so the editor sees it before switching the campaign on."""
        return campaign.missing_copy()

    def get_audience_label(self, campaign) -> str:
        return surveys.audience_label(campaign)


class AdminSurveyCampaignDetailSerializer(AdminSurveyCampaignSerializer):
    locked_questions = serializers.SerializerMethodField()

    class Meta(AdminSurveyCampaignSerializer.Meta):
        fields = (*AdminSurveyCampaignSerializer.Meta.fields, "locked_questions")

    def get_locked_questions(self, campaign) -> list[str]:
        """Ids that already have answers, so the form can render them read-only instead of
        letting someone hit a validation error on save."""
        if not campaign.pk:
            return []
        responses = SurveyResponse.objects.filter(campaign=campaign)
        return [
            question["id"]
            for question in campaign.questions
            if question.get("id") and responses.filter(answers__has_key=question["id"]).exists()
        ]


def _choice_options(choices) -> list[dict]:
    """A ``TextChoices`` set as the picker needs it, labels resolved from the lazy proxies."""
    return [{"value": value, "label": str(label)} for value, label in choices]


def _audience_options() -> dict:
    """Everything the campaign form's dropdowns offer"""
    return {
        "companies": surveys.company_audience_values(),
        "filters": surveys.audience_filter_choices(),
        "triggers": _choice_options(SurveyCampaign.Trigger.choices),
        "eligible_after_events": _choice_options(SurveyCampaign.EligibleAfterEvent.choices),
    }


def _campaign_queryset():
    return SurveyCampaign.objects.annotate(
        offered=Count("responses", distinct=True),
        answered=Count(
            "responses",
            filter=Q(responses__status=SurveyResponse.Status.SUBMITTED),
            distinct=True,
        ),
        rendered=Count(
            "responses",
            filter=Q(responses__shown_count__gt=0) | Q(responses__opened_at__isnull=False),
            distinct=True,
        ),
    )


def _saved_campaign_response(serializer, status_code: int):
    """Save, converting the model's own ValidationError into a 400 the form can render."""
    try:
        campaign = serializer.save()
    except ValidationError as e:
        errors = e.message_dict if hasattr(e, "message_dict") else {"non_field_errors": list(e.messages)}
        flat = [msg for msgs in errors.values() for msg in (msgs if isinstance(msgs, list) else [msgs])]
        return Response({"status": "error", "message": " ".join(flat), "errors": errors}, status=400)
    fresh = _campaign_queryset().get(pk=campaign.pk)
    return Response(AdminSurveyCampaignDetailSerializer(fresh).data, status=status_code)


@extend_schema(responses={200: AdminSurveyCampaignSerializer(many=True)})
@api_view(["GET", "POST"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_survey_campaigns(request):
    if request.method == "GET":
        campaigns = _campaign_queryset().order_by("-created_at")
        return Response(AdminSurveyCampaignSerializer(campaigns, many=True).data)

    serializer = AdminSurveyCampaignSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return _saved_campaign_response(serializer, 201)


@extend_schema(description="Companies and banner filters for the audience picker.")
@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_survey_campaign_options(request):
    return Response(_audience_options())


@extend_schema(responses={200: AdminSurveyCampaignDetailSerializer})
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_survey_campaign_detail(request, pk: int):
    campaign = get_object_or_404(_campaign_queryset(), pk=pk)

    if request.method == "GET":
        return Response(AdminSurveyCampaignDetailSerializer(campaign).data)

    if request.method == "DELETE":
        # Campaigns are retired with active=False; deleting one would orphan its answers,
        # which the PROTECT on SurveyResponse.campaign already refuses at the database level.
        if campaign.responses.exists():
            return Response(
                {
                    "status": "error",
                    "message": "This campaign has responses. Deactivate it instead of deleting it.",
                },
                status=400,
            )
        campaign.delete()
        return Response(status=204)

    serializer = AdminSurveyCampaignSerializer(campaign, data=request.data, partial=request.method == "PATCH")
    serializer.is_valid(raise_exception=True)
    return _saved_campaign_response(serializer, 200)


class AdminSurveyResponseSerializer(serializers.ModelSerializer):
    campaign_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()

    class Meta:
        model = SurveyResponse
        fields = (
            "id",
            "campaign_id",
            "campaign_name",
            "user_id",
            "user_email",
            "status",
            "delivery_channel",
            "shown_count",
            "opened_at",
            "answers",
            "questions",
            "created_at",
            "submitted_at",
        )

    def get_campaign_name(self, obj) -> str:
        return obj.campaign.name or obj.campaign.slug

    def get_user_email(self, obj) -> str:
        return obj.user.email or ""

    def get_questions(self, obj) -> list:
        """The campaign's questions, so the sheet can render answers without a second fetch.

        Rating questions carry their effective scale, so older rows that fall back to the
        campaign scale are not rendered against a guessed one.
        """
        return [
            {**question, "scale": rating_scale_for(question, obj.campaign)}
            if question.get("type") == QuestionType.RATING
            else question
            for question in obj.campaign.questions or []
        ]


def _campaign_filter_options() -> list[dict]:
    campaigns = SurveyCampaign.objects.order_by("name", "slug").only("id", "name", "slug")
    return [{"label": campaign.name or campaign.slug, "value": str(campaign.pk)} for campaign in campaigns]


def _status_filter_options() -> list[dict]:
    return [{"label": label, "value": value} for value, label in SurveyResponse.Status.choices]


@extend_schema(responses={200: AdminSurveyResponseSerializer(many=True)})
@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_survey_responses(request):
    """Paginated response rows for the admin table, filterable by campaign and status."""
    search = (request.GET.get("search") or "").strip()
    campaign = (request.GET.get("campaign") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    page = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 50))

    qs = SurveyResponse.objects.select_related("campaign", "user").order_by("-created_at")

    if campaign and campaign != "all":
        try:
            qs = qs.filter(campaign_id=int(campaign))
        except ValueError:
            qs = qs.none()

    valid_statuses = {choice.value for choice in SurveyResponse.Status}
    if status_filter and status_filter != "all" and status_filter in valid_statuses:
        qs = qs.filter(status=status_filter)

    if search:
        qs = qs.filter(user__email__icontains=search)

    paginated = get_paginated_format_v2(qs, page_size, page)
    paginated["results"] = AdminSurveyResponseSerializer(paginated["results"], many=True).data
    paginated["campaign_options"] = _campaign_filter_options()
    paginated["status_options"] = _status_filter_options()
    paginated["summary"] = None
    if campaign and campaign != "all":
        try:
            selected = SurveyCampaign.objects.filter(pk=int(campaign)).first()
        except ValueError:
            selected = None
        if selected is not None:
            paginated["summary"] = surveys.campaign_response_summary(selected)
    return Response(paginated)


api_urls = [
    path("api/surveys/pending", pending_survey, name="pending_survey_api"),
    path("api/surveys/<slug:slug>", survey_by_slug, name="survey_by_slug_api"),
    path("api/surveys/<int:response_id>/shown", mark_survey_shown, name="mark_survey_shown_api"),
    path("api/surveys/<int:response_id>/submit", submit_survey, name="submit_survey_api"),
    path("api/surveys/<int:response_id>/dismiss", dismiss_survey, name="dismiss_survey_api"),
    path("api/admin/survey_campaigns/", admin_survey_campaigns, name="admin_survey_campaigns_api"),
    path(
        "api/admin/survey_campaigns/options/",
        admin_survey_campaign_options,
        name="admin_survey_campaign_options_api",
    ),
    path(
        "api/admin/survey_campaigns/<int:pk>/",
        admin_survey_campaign_detail,
        name="admin_survey_campaign_detail_api",
    ),
    path(
        "api/admin/survey_responses/",
        admin_survey_responses,
        name="admin_survey_responses_api",
    ),
]
