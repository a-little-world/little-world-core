from dataclasses import dataclass

from translations import get_translation
from chat.consumers.messages import InMatchProposalAdded, InUnconfirmedMatchAdded
from django.db.models import Q
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer

from management import controller
from management.models.unconfirmed_matches import serialize_proposed_matches
from management.api.scores import score_between_db_update
from management.helpers import IsAdminOrMatchingUser
from management.helpers.detailed_pagination import get_paginated_format_v2

from management.models.matches import Match
from management.models.scores import TwoUserMatchingScore
from management.models.state import State
from management.models.unconfirmed_matches import ProposedMatch
from management.models.user import User
from video.models import LivekitSession, SerializeLivekitSession
from rest_framework import serializers
from chat.models import Chat, ChatConnections, ChatSerializer
from management.models.state import State
from management.models.profile import CensoredProfileSerializer
from management.api.match_journey_filter_list import determine_match_bucket
from management.api.utils_advanced import enrich_report_unmatch_with_user_info


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
            "report_unmatch": enrich_report_unmatch_with_user_info(instance.report_unmatch, instance),
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



@dataclass
class _MakeMatchSerializer:
    user1: int
    user2: int
    proposal: bool = True
    force: bool = False
    send_email: bool = True
    send_message: bool = True
    send_notification: bool = True


class MakeMatchSerializer(DataclassSerializer):
    class Meta:
        dataclass = _MakeMatchSerializer


@extend_schema(
    summary="Make a match",
    description="Make a match between two users",
    request=MakeMatchSerializer,
)
@permission_classes([IsAdminOrMatchingUser])
@api_view(["POST"])
def make_match(request):
    assert request.user.is_staff or request.user.state.has_extra_user_permission(
        State.ExtraUserPermissionChoices.MATCHING_USER
    ), "User is not allowed to match users"

    if (not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)) and (
        not request.user.is_staff
    ):
        return Response("User is not allowed to match users", status=status.HTTP_403_FORBIDDEN)

    serializer = MakeMatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    params = serializer.save()
    user1 = User.objects.get(pk=params.user1)
    user2 = User.objects.get(pk=params.user2)

    for user in [user1, user2]:
        if user not in request.user.state.managed_users.all():
            return Response(
                "User is not allowed to match these users, you don't have matching authority for them",
                status=status.HTTP_403_FORBIDDEN,
            )

    # check if matching score exists, else calculate it
    total_score, matchable, results, score = score_between_db_update(user1, user2)

    # 1 - if user is not matchable we may online contine by 'force'
    if (not matchable) and (not params.force):
        return Response({"message": "Users not matchable", "score_id": score.pk}, status=400)

    # 2 - check if users are already matched
    if Match.get_match(user1, user2).exists():
        return Response("Users are already matched", status=status.HTTP_400_BAD_REQUEST)

    # 3 - check what to send a 'proposal' or a 'direct match'
    if params.proposal:
        # 4 - check if a proposal already exists
        if ProposedMatch.objects.filter(
            Q(user1=user1, user2=user2) | Q(user1=user2, user2=user1), closed=False
        ).exists():
            return Response("Proposal already exists", status=status.HTTP_400_BAD_REQUEST)

        # ... create the proposal
        proposal = controller.create_user_matching_proposal(
            {user1, user2},
            send_confirm_match_email=params.send_email,
        )
        learner = proposal.get_learner()
        matches = serialize_proposed_matches([proposal], learner)

        TwoUserMatchingScore.objects.filter(user1=user1, user2=user2).delete()
        # Now update all matchable = False scores entries that have user1 or user2 as a user and are matchable = True
        TwoUserMatchingScore.objects.filter(
            (Q(user1=user1) | Q(user2=user1) | Q(user1=user2) | Q(user2=user2)) & Q(matchable=True)
        ).update(matchable=False)

        InMatchProposalAdded(matches[0]).send(learner.hash)

        learner.sms(request.user, get_translation("sms.proposal_message", lang="de"))

        return Response(f"Matching Proposal Created")
    else:
        # Perfor a full match directly
        match_obj = controller.match_users(
            {user1, user2},
            send_email=params.send_email,
            send_message=params.send_message,
            send_notification=params.send_notification,
        )

        user1.state.change_searching_state(State.SearchingStateChoices.IDLE)
        user2.state.change_searching_state(State.SearchingStateChoices.IDLE)

        for user in [user1, user2]:
            matches = AdvancedUserMatchSerializer([match_obj], many=True, context={"user": user}).data
            InUnconfirmedMatchAdded(matches[0]).send(user.hash)

        return Response("Users sucessfully matched")


@extend_schema(
    summary="Get a match",
    description="Get a match by the partner's hash",
    responses={
        200: inline_serializer("ProfileGetMatch", {"category": "string", "match": AdvancedUserMatchSerializer}),
        400: "Bad request",
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_match(request, partner_hash):
    # 1 - get the match
    match = Match.objects.filter(
        Q(user1=request.user, user2__hash=partner_hash) | Q(user2=request.user, user1__hash=partner_hash), active=True
    )

    if not match.exists():
        return Response("Match not found", status=status.HTTP_400_BAD_REQUEST)
    else:
        match = match.first()

    # 2 - categorize the match, the frontend needs to know if it's a 'confirmed', 'unconfirmed' or 'support' match
    category = "confirmed" if match.confirmed else "unconfirmed"
    if match.support_matching and (
        not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
    ):
        # A match isn't shown as 'support' if the requesting user him self is a support user
        category = "support"

    serialized = AdvancedUserMatchSerializer(match, context={"user": request.user}).data

    return Response({"category": category, "match": serialized})


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
