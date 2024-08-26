from management.helpers import IsAdminOrMatchingUser
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_dataclasses.serializers import DataclassSerializer
from management.models.state import State
from management.models.user import User
from dataclasses import dataclass
from django.db.models import Q
from rest_framework.response import Response
from rest_framework import status
from management.models.unconfirmed_matches import ProposedMatch
from management.api.scores import score_between_db_update
from management import controller
from management.models.matches import Match
from management.api.user_data import AdvancedUserMatchSerializer
from management.api.user_data import serialize_proposed_matches
from chat.consumers.messages import InMatchProposalAdded, InUnconfirmedMatchAdded
from drf_spectacular.utils import extend_schema, inline_serializer
from management.models.scores import TwoUserMatchingScore


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
    assert request.user.is_staff or request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER), "User is not allowed to match users"

    if (not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)) and (not request.user.is_staff):
        return Response("User is not allowed to match users", status=status.HTTP_403_FORBIDDEN)

    serializer = MakeMatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    params = serializer.save()
    user1 = User.objects.get(pk=params.user1)
    user2 = User.objects.get(pk=params.user2)

    for user in [user1, user2]:
        if user not in request.user.state.managed_users.all():
            return Response("User is not allowed to match these users, you don't have matching authority for them", status=status.HTTP_403_FORBIDDEN)

    # check if matching score exists, else calculate it
    total_score, matchable, results, score = score_between_db_update(user1, user2)

    # 1 - if user is not matchable we may online contine by 'force'
    if (not matchable) and (not params.force):
        return Response({"message": "Users not matchable", "score_id": score.pk}, status=400)

    # 2 - check if users are already matched
    if controller.are_users_matched({user1, user2}):
        return Response("Users are already matched", status=status.HTTP_400_BAD_REQUEST)

    # 3 - check what to send a 'proposal' or a 'direct match'
    if params.proposal:
        # 4 - check if a proposal already exists
        if ProposedMatch.objects.filter(Q(user1=user1, user2=user2) | Q(user1=user2, user2=user1), closed=False).exists():
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
        TwoUserMatchingScore.objects.filter((Q(user1=user1) | Q(user2=user1) | Q(user1=user2) | Q(user2=user2)) & Q(matchable=True)).update(matchable=False)

        InMatchProposalAdded(matches[0]).send(learner.hash)
        return Response("Matching Proposal Created")
    else:
        # Perfor a full match directly
        match_obj = controller.match_users({user1, user2}, send_email=params.send_email, send_message=params.send_message, send_notification=params.send_notification)

        user1.state.change_searching_state(State.MatchingStateChoices.IDLE)
        user2.state.change_searching_state(State.MatchingStateChoices.IDLE)

        for user in [user1, user2]:
            matches = AdvancedUserMatchSerializer([match_obj], many=True, context={"user": user}).data
            InUnconfirmedMatchAdded(matches[0]).send(user.hash)

        return Response("Users sucessfully matched")


@extend_schema(summary="Get a match", description="Get a match by the partner's hash", responses={200: inline_serializer("ProfileGetMatch", {"category": "string", "match": AdvancedUserMatchSerializer}), 400: "Bad request"})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_match(request, partner_hash):
    # 1 - get the match
    match = Match.objects.filter(Q(user1=request.user, user2__hash=partner_hash) | Q(user2=request.user, user1__hash=partner_hash), active=True)

    if not match.exists():
        return Response("Match not found", status=status.HTTP_400_BAD_REQUEST)
    else:
        match = match.first()

    # 2 - categorize the match, the frontend needs to know if it's a 'confirmed', 'unconfirmed' or 'support' match
    category = "confirmed" if match.confirmed else "unconfirmed"
    if match.support_matching and (not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)):
        # A match isn't shown as 'support' if the requesting user him self is a support user
        category = "support"

    serialized = AdvancedUserMatchSerializer(match, context={"user": request.user}).data

    return Response({"category": category, "match": serialized})
