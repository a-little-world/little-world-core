from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from django.urls import path
from django.conf import settings
from django.db.models import Q
from django.core.paginator import Paginator
import urllib.parse

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import authentication, permissions, serializers, status
from management.models.notifications import Notification, SelfNotificationSerializer
from management.api.matches import AdvancedUserMatchSerializer
from management.models.matches import Match
from management.models.community_events import CommunityEvent, CommunityEventSerializer
from management.models.state import State, FrontendStatusSerializer
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
from management.models.profile import SelfProfileSerializer
from management.api.options import get_options_dict
from management.api.user_data import serialize_notifications, serialize_community_events
from management.models.unconfirmed_matches import serialize_proposed_matches
from management.helpers.detailed_pagination import get_paginated_format_v2
from management.models.unconfirmed_matches import ProposedMatch
from chat.models import Chat, ChatSerializer
from video.models import LivekitSession, SerializeLivekitSession


def get_user_data(user):
    """
    Returns user data similar to the original user_data function.
    """
    user_state = user.state
    user_profile = user.profile

    pre_match_appointent = None
    pre_matching_app = PreMatchingAppointment.objects.filter(user=user).first()
    if pre_matching_app:
        pre_match_appointent = PreMatchingAppointmentSerializer(pre_matching_app).data

    cal_data_link = None
    if hasattr(settings, "CAL_COM_PROFILE_LINK") and settings.CAL_COM_PROFILE_LINK:
        # encode the email to url safe string
        cal_data_link = settings.CAL_COM_PROFILE_LINK.replace(
            "{email}", urllib.parse.quote(user.email)
        )

    # Get video call join link if available
    pre_call_join_link = None
    try:
        if pre_matching_app and pre_matching_app.call_room:
            if pre_matching_app.call_room.join_link:
                pre_call_join_link = pre_matching_app.call_room.join_link
    except Exception:
        pass

    # User data including profile, permissions, and status
    profile_data = SelfProfileSerializer(user_profile).data

    return {
        "id": str(user.hash),
        "status": FrontendStatusSerializer(user_state).data,
        "isSupport": user_state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
        or user.is_staff,
        "isSearching": user_state.searching_state == State.SearchingStateChoices.SEARCHING,
        "email": user.email,
        "preMatchingAppointment": pre_match_appointent,
        "preMatchingCallJoinLink": pre_call_join_link,
        "calComAppointmentLink": cal_data_link,
        "hadPreMatchingCall": user_state.had_prematching_call,
        "emailVerified": user_state.email_authenticated,
        "userFormCompleted": user_state.user_form_state == State.UserFormStateChoices.FILLED,
        "profile": profile_data,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def notifications(request):
    """
    Returns notification data for the authenticated user.
    """
    page = int(request.GET.get("page", 1))
    items_per_page = int(request.GET.get("page_size", 10))
    
    try:
        read_notifications = get_paginated_format_v2(Notification.get_read_notifications(request.user), items_per_page, page)
        read_notifications["results"] = serialize_notifications(read_notifications["results"])

        unread_notifications = get_paginated_format_v2(Notification.get_unread_notifications(request.user), items_per_page, page)
        unread_notifications["results"] = serialize_notifications(unread_notifications["results"])

        archived_notifications = get_paginated_format_v2(Notification.get_archived_notifications(request.user), items_per_page, page)
        archived_notifications["results"] = serialize_notifications(archived_notifications["results"])
        
        return Response({
            "unread": unread_notifications,
            "read": read_notifications,
            "archived": archived_notifications,
        })
    except Exception as e:
        return Response({"error": str(e)}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def matches(request):
    """
    Returns match data for the authenticated user.
    """
    page = int(request.GET.get("page", 1))
    items_per_page = int(request.GET.get("page_size", 10))
    user = request.user
    
    try:
        is_matching_user = user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
        
        empty_list = get_paginated_format_v2(Match.objects.none(), items_per_page, 1)
        
        confirmed_matches = get_paginated_format_v2(Match.get_confirmed_matches(user), items_per_page, 1 if is_matching_user else page)
        confirmed_matches["results"] = AdvancedUserMatchSerializer(
            confirmed_matches["results"], many=True, context={"user": user}
        ).data

        unconfirmed_matches = get_paginated_format_v2(Match.get_unconfirmed_matches(user), items_per_page, 1)
        unconfirmed_matches["results"] = AdvancedUserMatchSerializer(
            unconfirmed_matches["results"], many=True, context={"user": user}
        ).data

        support_matches = get_paginated_format_v2(Match.get_support_matches(user), items_per_page, page if is_matching_user else 1)
        support_matches["results"] = AdvancedUserMatchSerializer(
            support_matches["results"], many=True, context={"user": user}
        ).data

        proposed_matches = get_paginated_format_v2(ProposedMatch.get_open_proposals_learner(user), items_per_page, 1)
        proposed_matches["results"] = serialize_proposed_matches(proposed_matches["results"], user)
        
        return Response({
            # Switch case here cause for support users all matches are 'support' matches :D
            "support": empty_list if is_matching_user else support_matches,
            "confirmed": support_matches if is_matching_user else confirmed_matches,
            "unconfirmed": unconfirmed_matches,
            "proposed": proposed_matches,
        })
    except Exception as e:
        return Response({"error": str(e)}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def community_events(request):
    """
    Returns community events data for the authenticated user.
    """
    page = int(request.GET.get("page", 1))
    items_per_page = int(request.GET.get("page_size", 10))
    user = request.user
    
    try:
        events = get_paginated_format_v2(CommunityEvent.get_active_events_for_user(user), items_per_page, page)
        events["results"] = serialize_community_events(events["results"])
        
        return Response(events)
    except Exception as e:
        return Response({"error": str(e)}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def api_options(request):
    """
    Returns API options including form options.
    """
    try:
        return Response(get_options_dict())
    except Exception as e:
        return Response({"error": str(e)}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def firebase_config(request):
    """
    Returns Firebase configuration for the client.
    """
    try:
        return Response({
            "firebaseClientConfig": settings.FIREBASE_CLIENT_CONFIG,
            "firebasePublicVapidKey": settings.FIREBASE_PUBLIC_VAPID_KEY,
        })
    except Exception as e:
        return Response({"error": str(e)}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def active_call_rooms(request):
    """
    Returns active call rooms for the authenticated user.
    """
    user = request.user
    
    try:
        # find all active calls
        all_active_rooms = LivekitSession.objects.filter(
            Q(room__u1=user, is_active=True, u2_active=True, u1_active=False)
            | Q(room__u2=user, is_active=True, u1_active=True, u2_active=False)
        )
        
        return Response(SerializeLivekitSession(all_active_rooms, context={"user": user}, many=True).data)
    except Exception as e:
        return Response({"error": str(e)}, status=400)


@extend_schema(
    responses=inline_serializer(
        name="UserData",
        fields={
            "id": serializers.UUIDField(),
            "status": serializers.CharField(),
            "isSupport": serializers.BooleanField(),
            "isSearching": serializers.BooleanField(),
            "email": serializers.EmailField(),
            "preMatchingAppointment": PreMatchingAppointmentSerializer(required=False),
            "calComAppointmentLink": serializers.CharField(),
            "hadPreMatchingCall": serializers.BooleanField(),
            "emailVerified": serializers.BooleanField(),
            "userFormCompleted": serializers.BooleanField(),
            "profile": SelfProfileSerializer(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def user_profile(request):
    """
    Returns user profile data.
    """
    try:
        return Response(get_user_data(request.user))
    except Exception as e:
        return Response({"error": str(e)}, status=400)
    
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def api_translations(request):
    from translations import get_translation_catalog
    return Response(get_translation_catalog())

api_urls = [
    path("api/notifications", notifications, name="notifications_api"),
    path("api/matches", matches, name="matches_api"),
    path("api/community", community_events, name="community_events_api"),
    path("api/api_options", api_options, name="api_options_api"),
    path("api/firebase", firebase_config, name="firebase_config_api"),
    path("api/call_rooms", active_call_rooms, name="active_call_rooms_api"),
    path("api/user", user_profile, name="user_profile_api"),
    path("api/translations", api_translations, name="api_translations_api"),
]
