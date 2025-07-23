import urllib.parse
from dataclasses import dataclass

from chat.models import Chat, ChatConnections, ChatSerializer
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
from video.models import LivekitSession, SerializeLivekitSession

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


def get_paginated(query_set, items_per_page, page):
    pages = Paginator(query_set, items_per_page).page(page)
    return {
        "items": list(pages),
        "totalItems": pages.paginator.count,
        "itemsPerPage": items_per_page,
        "currentPage": page,
    }


def get_paginated_format_v2(query_set, items_per_page, page):
    pages = Paginator(query_set, items_per_page).page(page)
    return {
        "results": list(pages),
        "page_size": items_per_page,
        "pages_total": pages.paginator.num_pages,
        "page": page,
        "first_page": 1,
        "next_page": pages.next_page_number() if pages.has_next() else None,
        "previous_page": pages.previous_page_number() if pages.has_previous() else None,
    }


def determine_match_bucket(match_pk):
    try:
        match_categorie_buckets = [
            "special__support_matching",
            "match_journey_v2__unviewed",
            "match_journey_v2__one_user_viewed",
            "match_journey_v2__confirmed_no_contact",
            "match_journey_v2__confirmed_single_party_contact",
            "match_journey_v2__first_contact",
            "match_journey_v2__match_ongoing",
            "match_journey_v2__completed_match",
            "match_journey_v2__match_free_play",
            "match_journey_v2__never_confirmed",
            "match_journey_v2__no_contact",
            "match_journey_v2__user_ghosted",
            "match_journey_v2__contact_stopped",
            "match_journey_v2__reported_or_removed",
        ]
        bucket_map = {entry.name: entry for entry in MATCH_JOURNEY_FILTERS if entry.name in match_categorie_buckets}
        for bucket in match_categorie_buckets:
            if bucket_map[bucket].queryset(Match.objects.filter(pk=match_pk)).exists():
                return bucket
        return None
    except Exception as e:
        print(e)
        return None


class AdvancedUserMatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Match
        fields = ["uuid"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        assert "user" in self.context, "User must be passed in context"
        user = self.context["user"]
        partner = instance.get_partner(user)

        is_online = ChatConnections.is_user_online(partner)
        chat = Chat.get_or_create_chat(user, partner)
        chat_serialized = ChatSerializer(chat, context={"user": user}).data
        # fetch incoming calls that are currently active
        active_call_room = None
        active_sessions = LivekitSession.objects.filter(
            Q(room__u1=user, room__u2=partner, is_active=True, u1_active=True, u2_active=True)
            | Q(room__u1=user, room__u2=partner, is_active=True, u1_active=True, u2_active=True)
            | Q(room__u1=partner, room__u2=user, is_active=True, u1_active=True, u2_active=False)
            | Q(room__u1=partner, room__u2=user, is_active=True, u1_active=False, u2_active=True)
            | Q(room__u1=user, room__u2=partner, is_active=True, u1_active=True, u2_active=False)
            | Q(room__u1=user, room__u2=partner, is_active=True, u1_active=False, u2_active=True)
        )
        if active_sessions.exists():
            active_session = active_sessions.first()
            active_call_room = SerializeLivekitSession(active_session).data

        representation = {
            "id": str(instance.uuid),
            "chat": {**chat_serialized},
            "chatId": str(chat.uuid),
            "active": instance.active,
            "activeCallRoom": active_call_room,
            "report_unmatch": instance.report_unmatch,
            "partner": {
                "id": str(partner.hash),
                "isOnline": is_online,
                "isSupport": partner.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
                or partner.is_staff,
                **CensoredProfileSerializer(partner.profile).data,
            },
        }
        if "status" in self.context:
            representation["status"] = self.context["status"]

        if ("determine_bucket" in self.context) and self.context["determine_bucket"]:
            bucket = determine_match_bucket(instance.pk)
            if bucket is not None:
                representation["bucket"] = bucket
            else:
                representation["bucket"] = "unknown"

        return representation


def serialize_proposed_matches(matching_proposals, user):
    serialized = []
    for proposal in matching_proposals:
        partner = proposal.get_partner(user)
        rejected_by = None
        if proposal.rejected_by is not None:
            rejected_by = proposal.rejected_by.hash
        serialized.append(
            {
                "id": str(proposal.hash),
                "partner": {"id": str(partner.hash), **ProposalProfileSerializer(partner.profile).data},
                "status": "proposed",
                "closed": proposal.closed,
                "rejected_by": rejected_by,
                "rejected_at": proposal.rejected_at,
                "rejected": proposal.rejected,
                "expired": proposal.expired,
                "expires_at": proposal.expires_at,
            }
        )

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
        },
    ),
)
@permission_classes([IsAuthenticated])
@api_view(["GET"])
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


def frontend_data(user, items_per_page=10, request=None):
    user_state = user.state
    user_profile = user.profile

    is_matching_user = user_state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)

    community_events = get_paginated(CommunityEvent.get_active_events_for_user(user), items_per_page, 1)
    community_events["items"] = serialize_community_events(community_events["items"])

    confirmed_matches = get_paginated(Match.get_confirmed_matches(user), items_per_page, 1)
    confirmed_matches["items"] = AdvancedUserMatchSerializer(
        confirmed_matches["items"], many=True, context={"user": user}
    ).data

    unconfirmed_matches = get_paginated(Match.get_unconfirmed_matches(user), items_per_page, 1)
    unconfirmed_matches["items"] = AdvancedUserMatchSerializer(
        unconfirmed_matches["items"], many=True, context={"user": user}
    ).data

    support_matches = get_paginated(Match.get_support_matches(user), items_per_page, 1)
    support_matches["items"] = AdvancedUserMatchSerializer(
        support_matches["items"], many=True, context={"user": user}
    ).data

    proposed_matches = get_paginated(ProposedMatch.get_open_proposals_learner(user), items_per_page, 1)
    proposed_matches["items"] = serialize_proposed_matches(proposed_matches["items"], user)

    read_notifications = get_paginated(Notification.get_read_notifications(user), 3, 1)
    read_notifications["items"] = serialize_notifications(read_notifications["items"])

    unread_notifications = get_paginated(Notification.get_unread_notifications(user), 3, 1)
    unread_notifications["items"] = serialize_notifications(unread_notifications["items"])

    archived_notifications = get_paginated(Notification.get_archived_notifications(user), 3, 1)
    archived_notifications["items"] = serialize_notifications(archived_notifications["items"])

    empty_list = {
        "items": [],
        "totalItems": 0,
        "itemsPerPage": 0,
        "currentPage": 0,
    }

    ud = user_data(user)

    chats = Chat.get_chats(user)
    paginated_chats = get_paginated_format_v2(chats, items_per_page, 1)
    paginated_chats["results"] = ChatSerializer(paginated_chats["results"], many=True, context={"user": user}).data

    # find all active calls
    all_active_rooms = LivekitSession.objects.filter(
        Q(room__u1=user, is_active=True, u2_active=True, u1_active=False)
        | Q(room__u2=user, is_active=True, u1_active=True, u2_active=False)
    )

    frontend_data = {
        "user": ud,
        "communityEvents": community_events,
        "matches": {
            # Switch case here cause for support users all matches are 'support' matches :D
            "support": empty_list if is_matching_user else support_matches,
            "confirmed": support_matches if is_matching_user else confirmed_matches,
            "unconfirmed": unconfirmed_matches,
            "proposed": proposed_matches,
        },
        "notifications": {
            "unread": unread_notifications,
            "read": read_notifications,
            "archived": archived_notifications,
        },
        "apiOptions": get_options_dict(),
        "chats": paginated_chats,
        "activeCallRooms": SerializeLivekitSession(all_active_rooms, context={"user": user}, many=True).data,
        "firebaseClientConfig": settings.FIREBASE_CLIENT_CONFIG,
        "firebasePublicVapidKey": settings.FIREBASE_PUBLIC_VAPID_KEY,
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
@api_view(["POST"])
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

    authentication_classes = [authentication.SessionAuthentication, authentication.BasicAuthentication]
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
            confirmed_matches = get_paginated(matches, items_per_page, page)

            # Serialize matches data for the user
            confirmed_matches["items"] = AdvancedUserMatchSerializer(
                confirmed_matches["items"], many=True, context={"user": request.user}
            ).data

        except Exception:
            return Response({"code": 400, "error": "Page not Found"}, status=status.HTTP_400_BAD_REQUEST)

        # Return a successful response with the data
        return Response({"code": 200, "data": {"confirmed_matches": confirmed_matches}}, status=status.HTTP_200_OK)
