#
# implement: 
from management.views.admin_panel_v2 import IsAdminOrMatchingUser
from rest_framework.decorators import api_view, permission_classes
from rest_framework_dataclasses.serializers import DataclassSerializer
from management.models.state import State
from management.models.user import User
from dataclasses import dataclass
from rest_framework.response import Response
from rest_framework import status
from management.api.scores import score_between_db_update
from management import controller
from management.api.user_data import serialize_matches
from management.api.user_data import serialize_proposed_matches
from chat.consumers.messages import InMatchProposalAdded, InUnconfirmedMatchAdded

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

@permission_classes([IsAdminOrMatchingUser])
@api_view(['POST'])
def make_match(request):
    assert request.user.is_staff or request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER), "User is not allowed to match users"
    serializer = MakeMatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    params = serializer.save()
    user1 = User.objects.get(pk=params.user1)
    user2 = User.objects.get(pk=params.user2)

    for user in [user1, user2]:
        assert user in request.user.state.managed_users.all(), "User is not allowed to match users"

    # check if matching score exists, else calculate it
    total_score, matchable, results, score = score_between_db_update(user1, user2)

    # 1 - if user is not matchable we may online contine by 'force'
    if (not matchable) and (not params.force):
        return Response({
            "message": "Users not matchable",
            "score_id": score.pk
        }, status=400)

    # 2 - check if users are already matched
    if controller.are_users_matched({user1, user2}):
        return Response("Users are already matched", status=status.HTTP_400_BAD_REQUEST)

    # 3 - check what to send a 'proposal' or a 'direct match'
    if params.proposal:
        proposal = controller.create_user_matching_proposal(
            {user1, user2},
            send_confirm_match_email=params.send_email,
        )
        learner = proposal.get_learner()
        matches = serialize_proposed_matches([proposal], learner)
        
        InMatchProposalAdded(matches[0]).send(learner.hash)
        return Response("Matching Proposal Created")
    else:
        # Perfor a full match directly
        match_obj = controller.match_users({user1, user2},
                               send_email=params.send_email,
                               send_message=params.send_message,
                               send_notification=params.send_notification)

        user1.state.change_searching_state(
            State.MatchingStateChoices.IDLE)
        user2.state.change_searching_state(
            State.MatchingStateChoices.IDLE)
        
        InUnconfirmedMatchAdded(matches[0]).send(user.hash)

        for user in [user1, user2]:
            matches = serialize_matches([match_obj], user)
            InUnconfirmedMatchAdded(matches[0]).send(user.hash)

        return Response("Users sucessfully matched")
