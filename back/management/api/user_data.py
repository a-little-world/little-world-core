import urllib.parse
from dataclasses import dataclass

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import authentication, permissions, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_dataclasses.serializers import DataclassSerializer

from back.utils import transform_add_options_serializer
from management.api.match_journey_filter_list import MATCH_JOURNEY_FILTERS
from management.api.options import get_options_dict
from management.models.banner import Banner, BannerSerializer
from management.models.community_events import CommunityEvent, CommunityEventSerializer
from management.models.matches import Match
from management.models.notifications import Notification, SelfNotificationSerializer
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
from management.models.profile import CensoredProfileSerializer, ProposalProfileSerializer, SelfProfileSerializer
from management.models.state import FrontendStatusSerializer, State
from management.models.unconfirmed_matches import ProposedMatch
from management.helpers.detailed_pagination import get_paginated_format_v2







def serialize_community_events(events):
    serialized = []

    for event in events:
        serialized.append(CommunityEventSerializer(event).data)

    return serialized


def serialize_notifications(notifications):
    serialized = []

    for notification in notifications:
        serialized.append(SelfNotificationSerializer(notification).data)

    return serialized




def user_data(user):
    user_state = user.state
    user_profile = user.profile

    is_matching_user = user_state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)

    ProfileWOptions = transform_add_options_serializer(SelfProfileSerializer)
    profile_data = ProfileWOptions(user_profile).data
    del profile_data["options"]

    support_matches = get_paginated_format_v2(Match.get_support_matches(user), 10, 1)
    support_matches["items"] = AdvancedUserMatchSerializer(
        support_matches["items"], many=True, context={"user": user}
    ).data

    cal_data_link = "{calcom_meeting_id}?{encoded_params}".format(
        encoded_params=urllib.parse.urlencode(
            {"email": str(user.email), "hash": str(user.hash), "bookingcode": str(user.state.prematch_booking_code)}
        ),
        calcom_meeting_id=settings.DJ_CALCOM_MEETING_ID,
    )

    pre_match_appointent = PreMatchingAppointment.objects.filter(user=user).order_by("created")
    if pre_match_appointent.exists():
        pre_match_appointent = PreMatchingAppointmentSerializer(pre_match_appointent.first()).data

    else:
        pre_match_appointent = None

    # Prematching join link depends on the support user
    pre_call_join_link = None
    overwrite_pre_join_link = settings.PREMATCHING_CALL_JOIN_LINK

    if overwrite_pre_join_link:
        pre_call_join_link = overwrite_pre_join_link
    elif len(support_matches["items"]) > 0:
        pre_call_join_link = f"/app/call-setup/{support_matches['items'][0]['partner']['id']}/"

    # Retrieve the active banner for the specific user type
    banner_query = Banner.get_active_banner(user)

    banner = BannerSerializer(banner_query).data if banner_query else {}

    return {
        "id": user.hash,
        "banner": banner,
        "status": FrontendStatusSerializer(user_state).data["status"],
        "isSupport": is_matching_user,
        "isSearching": user_state.searching_state == State.SearchingStateChoices.SEARCHING,
        "email": user.email,
        "preMatchingAppointment": pre_match_appointent,
        "preMatchingCallJoinLink": pre_call_join_link,
        "calComAppointmentLink": cal_data_link,
        "hadPreMatchingCall": user_state.had_prematching_call,
        "emailVerified": user_state.email_authenticated,
        "userFormCompleted": user_state.user_form_state == State.UserFormStateChoices.FILLED,  # TODO: depricate
        "profile": profile_data,
    }