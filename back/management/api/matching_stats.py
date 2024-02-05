from rest_framework.decorators import api_view, authentication_classes, permission_classes
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from rest_framework.permissions import IsAuthenticated
from management.models.state import State
from management.models.profile import Profile
from management.views.admin_panel_v2 import get_staff_queryset, QuerySetEnum
from enum import Enum
from dataclasses import dataclass

class ScoringFunctionsEnum(Enum):
    users_waiting_for_match = "Users ( for current matching user ) that need a match."
    learners_waiting_for_match = "learners_waiting_for_match"
    percentage_of_learners_waiting_for_match = "percentage_of_learners_waiting_for_match"
    matchable_scores = "matchable_scores"
    unmatchable_scores = "unmatchable_scores"
    considerable_match_permutations = "considerable_match_permutations"
    
class ScoreTypesEnum(Enum):
    value = "value"
    percentage = "percentage"
    
@dataclass
class MatchingStatisticScore:
    scoring_function: str
    score_type: str
    data: dict
    
    def dict(self):
        return self.__dict__.copy()
    
def get_matching_statictic_score_function(request, scoring_function):
    """
    Calulates query values, some may be dependent on which users the call is 'matching-user' for  
    """
    if scoring_function == ScoringFunctionsEnum.users_waiting_for_match.name:

        needs_matching = get_staff_queryset(QuerySetEnum.needs_matching.name, request)
        return MatchingStatisticScore(scoring_function=ScoringFunctionsEnum.users_waiting_for_match.value,score_type=ScoreTypesEnum.value.value,data={
            "value": needs_matching.count()
        })
    if scoring_function == ScoringFunctionsEnum.learners_waiting_for_match.name:
        needs_matching = get_staff_queryset(QuerySetEnum.needs_matching.name, request)
        learners_needs_matching = needs_matching.filter(profile__user_type=Profile.TypeChoices.LEARNER)
        return MatchingStatisticScore(scoring_function=ScoringFunctionsEnum.learners_waiting_for_match.value ,score_type=ScoreTypesEnum.value.value, data={
            "value": learners_needs_matching.count()
        })
        
    if scoring_function == ScoringFunctionsEnum.percentage_of_learners_waiting_for_match.name:
        needs_matching = get_staff_queryset(QuerySetEnum.needs_matching.name, request)
        all_count = needs_matching.count()
        learners_needs_matching = needs_matching.filter(profile__user_type=Profile.TypeChoices.LEARNER)
        return MatchingStatisticScore(scoring_function=ScoringFunctionsEnum.percentage_of_learners_waiting_for_match.value,score_type=ScoreTypesEnum.percentage.value,data={
            "value": (learners_needs_matching.count() / all_count) * 100
        })
    if scoring_function == ScoringFunctionsEnum.matchable_scores.name:
        
        from management.models.scores import TwoUserMatchingScore
        count_matchable = TwoUserMatchingScore.objects.filter(matchable=True).count()
        return MatchingStatisticScore(
            scoring_function=ScoringFunctionsEnum.matchable_scores.value,
            score_type=ScoreTypesEnum.value.value,
            data={ "value": count_matchable })
    if scoring_function == ScoringFunctionsEnum.unmatchable_scores.name:
        
        from management.models.scores import TwoUserMatchingScore
        count_unmatchable = TwoUserMatchingScore.objects.filter(matchable=False).count()
        return MatchingStatisticScore(
            scoring_function=ScoringFunctionsEnum.unmatchable_scores.value,
            score_type=ScoreTypesEnum.value.value,
            data={ "value": count_unmatchable })

    if scoring_function == ScoringFunctionsEnum.considerable_match_permutations.name:
        from management.models.scores import TwoUserMatchingScore
        needs_matching = get_staff_queryset(QuerySetEnum.needs_matching.name, request)
        # we we need to annotate user1.id and user2.id, get a set of that and count possible matches of two
        user_id_set = set(needs_matching.values_list('id', flat=True))
        combinations = len(user_id_set) * (len(user_id_set) - 1) / 2
        return MatchingStatisticScore(
            scoring_function=ScoringFunctionsEnum.considerable_match_permutations.value,
            score_type=ScoreTypesEnum.value.value,
            data={ "value": combinations })
    else:
        raise ValueError("Invalid scoring function")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_quick_statistics(request):
    assert request.user.is_staff or request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
    
    scoring_function = request.query_params.get('scoring_function', None)
    if scoring_function is not None:
        score_function = get_matching_statictic_score_function(request, scoring_function)
        return Response(score_function.dict())
    # TODO calculate all scores
    return Response("No scoring function provided", status=400)
    