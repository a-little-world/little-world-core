import django.contrib.auth.password_validation as pw_validation
import urllib.parse
from copy import deepcopy
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
from rest_framework_dataclasses.serializers import DataclassSerializer
from chat.models import ChatSerializer, Chat, ChatInModelSerializer
from management.models.state import FrontendStatusSerializer
from django.core.paginator import Paginator
from drf_spectacular.types import OpenApiTypes
from datetime import datetime
from django.conf import settings
from chat.api.chats import ChatsModelViewSet
from copy import deepcopy
from django.core import exceptions
from django.utils.module_loading import import_string
from rest_framework.decorators import api_view, schema, throttle_classes, permission_classes
from rest_framework import authentication, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie, vary_on_headers
from rest_framework import serializers, status
from rest_framework.throttling import UserRateThrottle
from dataclasses import dataclass
from back.utils import transform_add_options_serializer
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import inline_serializer
from management.models.profile import (
    ProfileSerializer, SelfProfileSerializer,
    CensoredProfileSerializer,
    ProposalProfileSerializer,
)
from management.models.unconfirmed_matches import (
    UnconfirmedMatch,
)
from management.models.state import (
    State,
    StateSerializer, SelfStateSerializer,
)
from management.models.community_events import (
    CommunityEvent,
    CommunityEventSerializer,
)
from management.models.settings import (
    SelfSettingsSerializer,
)
from management.models.notifications import (
    SelfNotificationSerializer, NotificationSerializer, Notification,
)
from management.models.user import (
    UserSerializer, SelfUserSerializer,
    CensoredUserSerializer,
)
from management.models.matches import Match
from management.api.community_events import get_all_comunity_events_serialized
from management.models.unconfirmed_matches import get_unconfirmed_matches

from management.controller import get_user_models

def get_paginated(query_set, items_per_page, page):
    pages = Paginator(query_set, items_per_page).page(page)
    return {
        "items": list(pages),
        "totalItems": pages.paginator.count,
        "itemsPerPage": items_per_page,
        "currentPage": page,
    }

def serialize_matches(matches, user):
    serialized = []
    for match in matches:

        partner = match.get_partner(user)

        # Check if the partner is online
        from chat.models import ChatConnections
        is_online = ChatConnections.is_user_online(partner)
        
        chat = Chat.get_or_create_chat(user, partner)
        chat_serialized = ChatInModelSerializer(chat, context={'user': user}).data

        serialized.append({
            "id": str(match.uuid),
            "chat": {
                **chat_serialized
            },
            "chatId": str(chat.uuid),
            "partner": {
                "id": str(partner.hash),
                "isOnline": is_online,
                "isSupport": partner.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER) or partner.is_staff,
                **CensoredProfileSerializer(partner.profile).data
            }
        })

    return serialized

def serialize_proposed_matches(matching_proposals, user):
    serialized = []
    for proposal in matching_proposals:

        partner = proposal.get_partner(user)
        serialized.append({
            "id": str(proposal.hash),
            "partner": {
                "id": str(partner.hash),
                **ProposalProfileSerializer(partner.profile).data
            }
        })

    return serialized

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
        }
    ),
)
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def user_data_api(request):
    return Response(user_data(request.user))

def user_data(user):
    user_state = user.state
    user_profile = user.profile
    
    is_matching_user = user_state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)

    ProfileWOptions = transform_add_options_serializer(SelfProfileSerializer)
    profile_data = ProfileWOptions(user_profile).data
    del profile_data["options"]

    
    support_matches = get_paginated(Match.get_support_matches(user), 10, 1)
    support_matches["items"] = serialize_matches(support_matches["items"], user)
    
    
    cal_data_link = "{calcom_meeting_id}?{encoded_params}".format(first_name=user.profile.first_name,encoded_params=urllib.parse.urlencode({
                        "email": str(user.email),
                        "hash": str(user.hash),
                        "bookingcode": str(user.state.prematch_booking_code)
    }), calcom_meeting_id=settings.DJ_CALCOM_MEETING_ID)
    
    
    pre_match_appointent = PreMatchingAppointment.objects.filter(user=user).order_by("created")
    if pre_match_appointent.exists():
        pre_match_appointent = PreMatchingAppointmentSerializer(pre_match_appointent.first()).data
    else:
        pre_match_appointent = None

    # Prematching join link depends on the support user
    pre_call_join_link = None
    if len(support_matches['items']) > 0:
        pre_call_join_link = f"/app/call-setup/{support_matches['items'][0]['partner']['id']}/"
    
    return {
            "id": user.hash,
            "status": FrontendStatusSerializer(user_state).data["status"],
            "isSupport": is_matching_user,
            "isSearching": user_state.matching_state == State.MatchingStateChoices.SEARCHING,
            "email": user.email,
            "preMatchingAppointment": pre_match_appointent,
            'preMatchingCallJoinLink': pre_call_join_link,
            "calComAppointmentLink": cal_data_link,
            "hadPreMatchingCall": user_state.had_prematching_call,
            "emailVerified": user_state.email_authenticated,
            "userFormCompleted": user_state.user_form_state == State.UserFormStateChoices.FILLED, # TODO: depricate
            "profile": profile_data,
    }

def frontend_data(user, items_per_page=10, request=None):

    user_state = user.state
    user_profile = user.profile
    
    is_matching_user = user_state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)

    community_events = get_paginated(CommunityEvent.get_all_active_events(), items_per_page, 1)
    community_events["items"] = serialize_community_events(community_events["items"])

    confirmed_matches = get_paginated(Match.get_confirmed_matches(user), items_per_page, 1)
    confirmed_matches["items"] = serialize_matches(confirmed_matches["items"], user)

    unconfirmed_matches = get_paginated(Match.get_unconfirmed_matches(user), items_per_page, 1)
    unconfirmed_matches["items"] = serialize_matches(unconfirmed_matches["items"], user)

    support_matches = get_paginated(Match.get_support_matches(user), items_per_page, 1)
    support_matches["items"] = serialize_matches(support_matches["items"], user)

    proposed_matches = get_paginated(UnconfirmedMatch.get_open_proposals(user), items_per_page, 1)
    proposed_matches["items"] = serialize_proposed_matches(proposed_matches["items"], user)

    read_notifications = get_paginated(Notification.get_read_notifications(user), items_per_page, 1)
    read_notifications["items"] = serialize_notifications(read_notifications["items"])

    unread_notifications = get_paginated(Notification.get_unread_notifications(user), items_per_page, 1)
    unread_notifications["items"] = serialize_notifications(unread_notifications["items"])

    archived_notifications = get_paginated(Notification.get_archived_notifications(user), items_per_page, 1)
    archived_notifications["items"] = serialize_notifications(archived_notifications["items"])

    empty_list = {
        "items": [],
        "totalItems": 0,
        "itemsPerPage": 0,
        "currentPage": 0,
    }

    ProfileWOptions = transform_add_options_serializer(SelfProfileSerializer)
    profile_data = ProfileWOptions(user_profile).data

    profile_options = profile_data["options"]
    
    ud = user_data(user)

    frontend_data = {
        "user": ud,
        "communityEvents": community_events,
        "matches": {
            # Switch case here cause for support users all matches are 'support' matches :D
            "support": empty_list if is_matching_user else support_matches,
            "confirmed" : support_matches if is_matching_user else confirmed_matches,
            "unconfirmed": unconfirmed_matches,
            "proposed": proposed_matches,
        },
        "notifications": {
            "unread": unread_notifications,
            "read": read_notifications,
            "archived": archived_notifications,
        },
        "apiOptions": {
            "profile": profile_options,
        },
        "incomingCalls": [
            # TODO: incoming calls should also be populated if one of the matches already is in a video call
            # This enable the pop-up to also show after login when the match already is in the video call
            # { "userId": "592a5cc9-77f9-4f18-8354-25fa56e1e792-c9dcfc91-865f-4371-b695-b00bd1967c27"}
        ],
    }


    return frontend_data



@dataclass
class UserDataV2Params:
    items_per_page: int = 10


class ConfirmMatchSerializer(DataclassSerializer):
    items_per_page = serializers.IntegerField(required=False, default=10)
    class Meta:
        dataclass = UserDataV2Params


@extend_schema(
    request=ConfirmMatchSerializer(many=False),
)
@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def user_data_v2(request):

    serializer = ConfirmMatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    params = serializer.save()

    return Response(frontend_data(request.user, params.items_per_page))


class ConfirmedDataApi(APIView):
    """
    Returns the Confirmed matches data for a given user.
    """
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(name="page", type=int, description="Page number for pagination"),
            OpenApiParameter(name="itemsPerPage", type=int, description="Number of items per page"),
        ],
    )

    def get(self, request):
        """
        Handle GET requests to retrieve confirmed matches data for the user.
        """
        page = int(request.GET.get("page", 1))
        items_per_page = int(request.GET.get("itemsPerPage", 10))

        is_matching_user = request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)

        try:
            # Retrieve confirmed matches using a utility function
            if is_matching_user:
                # Cause for support users all matches are 'support' matches we return them as confirmed matches
                matches = Match.get_support_matches(request.user)
            else:
                matches = Match.get_confirmed_matches(request.user)
            confirmed_matches = get_paginated(
                matches,
                items_per_page,
                page
            )

            # Serialize matches data for the user
            confirmed_matches["items"] = serialize_matches(
                confirmed_matches["items"],
                request.user
            )

        except Exception as e:
            return Response({"code":400, "error": "Page not Found"}, status=status.HTTP_400_BAD_REQUEST)

        # Return a successful response with the data
        return Response({"code": 200, "data": {"confirmed_matches": confirmed_matches}}, status=status.HTTP_200_OK)