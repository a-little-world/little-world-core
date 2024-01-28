"""
Checkt that ar implemented & active:

Generaly every function can be switched (on/off) and output a `score`, `weight`, `unmatchable` (bool) and `markdown_info` (str).
Check should generaly be onmi directional (user1 vs user2) and (user2 vs user1) and return the same result.
In the end all scores are weighted and summed up, a final report is generated, any `unmatchable` will cause a `-> unmatchable` result.

- [o] Learner vs Vounteer ( checkId: `volunteer_vs_learner` )
Must be match between learner and volunteer, else `-> unmatchable`

- [o] Gender Check ( checkId: `gender` )
> this is based on the `profile.gender` and `profile.partner_gender` fields
generaly `user.gender.MALE` with `other.partner_gender.FEMALE` & vice-verca causes `-> unmatchable`
If both `user.gender == other.partner_gender` AND `other.gender == user.partner_gender` then `+20` score
then `user.gender.ANY` with `user.partner_gender.ANY` gives a score of `10`
while `user.gender.MALE (or FEMALE)` with `user.gender_partne.ANY` will give a score of `5`

- [ ] How to Communicate ( checkId: `speech_medium` )
> this considers `profile.speech_medium`
if `user.speech_medium === other.speech_medium` then `+ 40 score`
if `user.speech_medium.VIDEO and other.speech_medium is AUDIO` then `-> unmatchable`
if `user.speech_medium.ANY and other.speech_medium is AUDIO` then `-> unmatchable`
Last one is a little try and caused some users to have very limited options in the past

- [o] distance ( checkId: `postal_code_distance` )
Perforing a simple postal code distance estimation using [pgeocode](https://github.com/symerio/pgeocode)
then table based scoring:
km disance `{"<50": 50, "<100": 40, "<200": 30, "<300": 20, "<400": 10, "<500": 5, ">500": 0}`

- [o] Time Slot Overlap ( checkId: `time_slot_overlap` )
Table based scores amount overlaps
`{"<=0": -15, "=1: 15, "=2": 25, "=3": 29, "=4": 32, "=5": 35, ">=6": 37}

- [o] Language Level ( checkId: `language_level` )
> this considers the `profile.lang_skill` and `profile.min_lang_level_partner`
So if `user.lang_skill["german"]` is lower than `other.min_lang_level_partner` then `-> unmatchable`

- [o] Interests Overlap ( checkId: `interest_overlap` )
5 points per common interest, max 30 points


Inactive Checks / Not implemented for now

- Should partner be close check ( as we don't have the form field for it in atm )

- [ ] Time Searching ( checkId: `time_searching` )
To give a slight advantage to users that have been searching for a longer time
days searching `{"=<5": 0, "<10": 5, "<20": 10, "<30": 15, ">30": 40}

- should match be near?
"""
from typing import Any
from datetime import datetime, timedelta, timezone
from back.utils import CoolerJson
from enum import Enum
import json
from django.conf import settings
from django.urls import path, re_path
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from openai import OpenAI
from management.models.state import State
from management.models.profile import Profile
from rest_framework import serializers
from dataclasses import dataclass
from management.models.scores import TwoUserMatchingScore
from management.models.user import User
from rest_framework.permissions import IsAuthenticated
from management.tasks import matching_algo_v2
import dataclasses
import os

@dataclass
class ScoreBetweenDataclass:
    user1: int
    user2: int

class ScoreBetweenSerializer(DataclassSerializer):
    class Meta:
        dataclass = ScoreBetweenDataclass
    
@dataclass
class ScoringFuctionResult:
    matchable: bool
    score: float = 0.0
    weight: float = 1.0
    markdown_info: str = ""
    
class ScoringFunctionsEnum(Enum):
    language_level = "language_level"
    learner_vs_volunteer = "learner_vs_volunteer"
    time_slot_overlap = "time_slot_overlap"
    postal_code_distance = "postal_code_distance"
    gender = "gender"
    interest_overlap = "interest_overlap"
    speech_medium = "speech_medium"
    
    
class ScoringBase():
    
    def __init__(
            self, 
            user1, 
            user2,
            ) -> None:
        self.user1 = user1
        self.user2 = user2
        # register scoring functions
        self.scoring_fuctions = {
            ScoringFunctionsEnum.language_level: self.score__language_level,
            ScoringFunctionsEnum.learner_vs_volunteer: self.score__volunteer_vs_learner,
            ScoringFunctionsEnum.time_slot_overlap: self.score__time_slot_overlap,
            ScoringFunctionsEnum.postal_code_distance: self.score__postal_code_distance,
            ScoringFunctionsEnum.gender: self.score__gender,
            ScoringFunctionsEnum.interest_overlap: self.score__interest_overlap,
        }
    
    def score__time_slot_overlap(self):
        """
        Table based scores amount overlaps
        `{"<=0": -15, "=1: 15, "=2": 25, "=3": 29, "=4": 32, "=5": 35, ">=6": 37}
        """
        slots1 = self.user1.profile.availability
        slots2 = self.user2.profile.availability
        from management.validators import DAYS, SLOTS
        amnt_common_slots = 0
        common_slots = {}

        for day in DAYS:
            for slot in SLOTS:
                if day in slots1 and day in slots2 and slot in slots1[day] and slot in slots2[day]:
                    common_slots[day] = common_slots.get(day, []) + [slot]
                    amnt_common_slots += 1
        conditions = [[lambda x: x <= 0, -15], [lambda x: x == 1, 15], [lambda x: x == 2, 25], [lambda x: x == 3, 29], [lambda x: x == 4, 32], [lambda x: x == 5, 35], [lambda x: x >= 6, 37]]
        for cond in conditions:
            if cond[0](amnt_common_slots):
                return ScoringFuctionResult(matchable=True, score=cond[1], weight=1.0, markdown_info=f"Common slots: ({str(amnt_common_slots)}) {str(common_slots)} (score: {cond[1]})")
        return ScoringFuctionResult(matchable=True, score=0, weight=1.0, markdown_info=f"Common slots: ({str(amnt_common_slots)}) {str(common_slots)} (score: 0)")
    
    def score__volunteer_vs_learner(self):
        """
Simple chat the we match only volunteers and learners! 
        """
        oppsite = any([self.user1.profile.user_type == Profile.TypeChoices.LEARNER and self.user2.profile.user_type ==
                       Profile.TypeChoices.VOLUNTEER,
                       self.user1.profile.user_type == Profile.TypeChoices.VOLUNTEER and self.user2.profile.user_type ==
                       Profile.TypeChoices.LEARNER])
        msg = "Volunteer + Learner can be machted :white_check_mark:" + "\n"
        if not oppsite:
            msg = "Volunteer + Volunteer or Learner + Learner can't be matched :x:" + "\n"
        return ScoringFuctionResult(matchable=oppsite, score=0, weight=1.0, markdown_info=msg)
    
    def score__language_level(self):
        volunteer = self.user1 if self.user1.profile.user_type == Profile.TypeChoices.VOLUNTEER else self.user2
        learner = self.user1 if self.user1.profile.user_type == Profile.TypeChoices.LEARNER else self.user2
        
        map_level_to_int = {
            Profile.LanguageSkillChoices.LEVEL_0: 0,
            Profile.LanguageSkillChoices.LEVEL_1: 1,
            Profile.LanguageSkillChoices.LEVEL_2: 2,
            Profile.LanguageSkillChoices.LEVEL_3: 3,
            Profile.MinLangLevelPartnerChoices.LEVEL_0: 0,
            Profile.MinLangLevelPartnerChoices.LEVEL_1: 1,
            Profile.MinLangLevelPartnerChoices.LEVEL_2: 2,
            Profile.MinLangLevelPartnerChoices.LEVEL_3: 3,
        }
        
        min_lang_level = volunteer.profile.min_lang_level_partner
        learner_german_level = list(filter(lambda x: x["lang"] == "german", learner.profile.lang_skill))[0]["level"]
        
        if map_level_to_int[min_lang_level] > map_level_to_int[learner_german_level]:
            return ScoringFuctionResult(matchable=False, score=0, weight=1.0, markdown_info=f"Volunteer has a higher min lang level than learner (score: 0)")
        else:
            return ScoringFuctionResult(matchable=True, score=30, weight=1.0, markdown_info=f"Volunteer has a lower min lang level than learner (score: 5)")
        
    
    def score__postal_code_distance(self):
        """
    Checks dependant on partner location choice the PLZ area distance
    `{"<50": 50, "<100": 40, "<200": 30, "<300": 20, "<400": 10, "<500": 5, ">500": 0}`
        """
        import pgeocode
        dist = pgeocode.GeoDistance('de')
        distance = dist.query_postal_code(self.user1.profile.postal_code, self.user2.profile.postal_code)
        conditions = [[lambda x: x < 50.0, 50.0], [lambda x: x < 100.0, 40.0], [lambda x: x < 200.0, 30.0], [lambda x: x < 300.0, 20.0], [lambda x: x < 400.0, 10.0], [lambda x: x < 500.0, 5.0], [lambda x: x >= 500.0, 0.0]]
        for cond in conditions:
            if cond[0](distance):
                return ScoringFuctionResult(matchable=True, score=cond[1], weight=1.0, markdown_info=f"Distance is {distance}km (score: {cond[1]})")
        return ScoringFuctionResult(matchable=True, score=0, weight=1.0, markdown_info=f"Distance is {distance}km (score: 0)")


    def score__gender(self):
        """
> this is based on the `profile.gender` and `profile.partner_gender` fields
generaly `user.gender.MALE` with `other.partner_gender.FEMALE` & vice-verca causes `-> unmatchable`
then `user.gender.ANY` with `user.partner_gender.ANY` gives a score of `30`
while `user.gender.MALE (or FEMALE)` with `user.gender_partne.ANY` will give a score of `5`
        """
        normalize_gender_choices = {
            Profile.GenderChoices.ANY: "any",
            Profile.GenderChoices.MALE: "male",
            Profile.GenderChoices.FEMALE: "female",
            Profile.PartnerGenderChoices.ANY: "any",
            Profile.PartnerGenderChoices.FEMALE: "female",
            Profile.PartnerGenderChoices.MALE: "male"
        } 

        gender1 = normalize_gender_choices[self.user1.profile.gender]
        partner_gender1 = normalize_gender_choices[self.user1.profile.partner_gender]
        gender2 = normalize_gender_choices[self.user2.profile.gender]
        partner_gender2 = normalize_gender_choices[self.user2.profile.partner_gender]
        
        if (gender1 == "female" and partner_gender2 == "male") or (gender2 == "female" and partner_gender1 == "male"):
            return ScoringFuctionResult(matchable=False, score=0, weight=1.0, markdown_info=f"Male but Female requested or vice versa :x: (score: 0)")
        if (partner_gender1 == "any") and (partner_gender2 == "any"):
            return ScoringFuctionResult(matchable=True, score=10.0, weight=1.0, markdown_info=f"Bot requested 'any' gender :white_check_mark: (score: 30)")
        if (((partner_gender1 == "male") and (gender2 == "male")) or ((partner_gender1 == "female") and (gender2 == "female"))) \
            and (((partner_gender2 == "male") and (gender1 == "male")) or ((partner_gender2 == "female") and (gender1 == "female"))):
            return ScoringFuctionResult(matchable=True, score=20.0, weight=1.0, markdown_info=f"All gender requests presisely fullfilled :white_check_mark: (score: 20)")
        if ((partner_gender1 == "any") and ((gender2 == "male") or (gender2 == "female"))) and ((partner_gender2 == "any") and ((gender1 == "male") or (gender1 == "female"))):
            return ScoringFuctionResult(matchable=True, score=5.0, weight=1.0, markdown_info=f"All gender requests fullfilledi ( some gender -> any match also contained ) :white_check_mark: (score: 5)")

    def score__interest_overlap(self):
        """
        We assigns some scores for overlapping interests
        But this can never cause 'unmatchable'
        """

        it1 = self.user1.profile.interests
        it2 = self.user2.profile.interests

        common_interests = set(it1).intersection(set(it2))
        amnt_common_interests = len(common_interests)

        conditions = [[lambda x: x == 0, 0], [lambda x: x == 1, 5], [lambda x: x == 2, 10], [lambda x: x == 3, 15], [lambda x: x == 4, 20], [lambda x: x == 5, 25], [lambda x: x >= 6, 30]]
        
        for cond in conditions:
            if cond[0](amnt_common_interests):
                return ScoringFuctionResult(matchable=True, score=cond[1], weight=1.0, markdown_info=f"Interests Overlap: {str(common_interests)} (score: {cond[1]})")
        
        return ScoringFuctionResult(matchable=True, score=0, weight=1.0, markdown_info=f"Interests Overlap (score: 0)")
    
    def score__speech_medium(self):
        speech_medium1 = self.user1.profile.speech_medium
        speech_medium2 = self.user2.profile.speech_medium
        
        if (speech_medium1 == Profile.SpeechMediumChoices.ANY and (speech_medium2 == Profile.SpeechMediumChoices.AUDIO or speech_medium2 == Profile.SpeechMediumChoices.VIDEO)) \
            or (speech_medium2 == Profile.SpeechMediumChoices.ANY and (speech_medium1 == Profile.SpeechMediumChoices.AUDIO or speech_medium1 == Profile.SpeechMediumChoices.VIDEO)):
            return ScoringFuctionResult(matchable=True, score=10, weight=1.0, markdown_info=f"Speech Medium: Any  :white_check_mark: (score: 10)")
        if speech_medium1 == speech_medium2:
            return ScoringFuctionResult(matchable=True, score=40, weight=1.0, markdown_info=f"Speech Medium: {speech_medium1} requested :white_check_mark: (score: 40)")

        return ScoringFuctionResult(matchable=False, score=0, weight=1.0, markdown_info=f"Speech Medium: {speech_medium1} requested but {speech_medium2} offered :x: (score: 0)")
    
    def calculate_score(self, raise_exception=False):
        
        results = []
        error_occured = False
        for score_function in list(self.scoring_fuctions.keys()):
            try:
                res = self.scoring_fuctions[score_function]()
                assert res, f"Score function must return a ScoringFuctionResult: {score_function} doesn't"
            except Exception as e:
                error_occured = True
                if raise_exception:
                    raise e
                print(f"Error in score function {score_function}:", e)
                res = ScoringFuctionResult(matchable=False, score=0, weight=1.0, markdown_info=f"ERROR in score function {score_function}: {e}")
            results.append({
                "score_function": score_function,
                "res": res
            })
            
        print("Results:", results) 
        total_score = sum([res["res"].score * res["res"].weight for res in results])
        matchable = all([res["res"].matchable for res in results])
        return total_score, matchable, results

def score_between_db_update(user1, user2):
    base = ScoringBase(user1, user2)
    total_score, matchable, results = base.calculate_score()
    
    score = TwoUserMatchingScore.get_or_create(user1, user2)
    score.score = total_score
    score.matchable = matchable
    score.scoring_results = json.loads(json.dumps(results, cls=CoolerJson))
    score.save()

    return total_score, matchable, results, score

@dataclass
class DispatchScoreCalculationDataclass:
    user: int
    
class DispatchScoreCalculationSerializer(DataclassSerializer):
    class Meta:
        dataclass = DispatchScoreCalculationDataclass

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dispatch_score_calculation(request):
    assert request.user.is_staff or request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
    
    serializer = DispatchScoreCalculationSerializer(request.data)
    serializers.is_valid(raise_exception=True)
    data = serializer.save()
    
    task = matching_algo_v2.delay(data["user"], 50)
    
    return Response({
            "msg": "Task dispatched scores will be written to db on task completion",
            "task_id": task.task_id,
            "view": f"/admin/django_celery_results/taskresult/?q={task.task_id}"
        })
    
    
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def calculate_score_between(request):
    assert request.user.is_staff or request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
    
    serializer = ScoreBetweenDataclass(request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.data
    
    user1 = User.objects.get(id=data["user1"])
    user2 = User.objects.get(id=data["user2"])

    total_score, matchable, results = score_between_db_update(user1, user2)
    return Response({
        "total_score": total_score,
        "matchable": matchable,
        "results": results
    })
    

    
def calculate_scores_user(user_pk, consider_only_registered_within_last_x_days=None):
    from management import controller
    from management.models.state import State
    from management.models.unconfirmed_matches import UnconfirmedMatch
    from django.db.models import Q
    from django.db.models import Exists, OuterRef

    usr = controller.get_user_by_pk(user_pk)
    
    all_users_to_consider = User.objects.annotate(
        has_open_proposal=Exists(
            UnconfirmedMatch.objects.filter(
                Q(user1=OuterRef('pk')) | Q(user2=OuterRef('pk')), closed=False
            )
        )
    ).filter(
        state__matching_state=State.MatchingStateChoices.SEARCHING,
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        is_staff=False,
        has_open_proposal=False
    ).exclude(
        id=usr.pk, 
        state__user_category__in=[State.UserCategoryChoices.SPAM, State.UserCategoryChoices.TEST]
    )

    if not (consider_only_registered_within_last_x_days is None):
        from django.utils import timezone
        today = timezone.now()
        x_days_ago = today - timedelta(days=consider_only_registered_within_last_x_days)
        all_users_to_consider = all_users_to_consider.filter(date_joined__gte=x_days_ago)
        
    
    # - We have to set the score of all users not to consider to 0
    all_users_not_to_consider = User.objects.annotate(
        to_consider=Exists(
            all_users_to_consider.filter(pk=OuterRef('id'))
        )
    ).filter(to_consider=False)

    total_considered_users = all_users_to_consider.count()
    total_unconsidered_users = all_users_not_to_consider.count()
    
    # we always delete all scores of unconsidered users, that way we assure that we don't blow database sizes!
    from management.models.scores import TwoUserMatchingScore
    cleaned_scores = TwoUserMatchingScore.objects.filter(
        (~Q(user1__in=all_users_to_consider) and Q(user2=usr)) | (~Q(user2__in=all_users_to_consider) and Q(user1=usr))
    )
    count_cleaned_scores = cleaned_scores.count()
    cleaned_scores.delete()
    

    print({
            'total_considered_users': total_considered_users,
            'total_unconsidered_users': total_unconsidered_users,
            'scores_cleaned': count_cleaned_scores,
            'progress': 0,
            "state": "starting"
        })
        
    for user in all_users_to_consider:
        score_between_db_update(usr, user)

        print({
                'total_considered_users': total_considered_users,
                'total_unconsidered_users': total_unconsidered_users,
                'scores_cleaned': count_cleaned_scores,
                'progress': 0,
                "state": "processing",
                "current_user": user.pk
            })
            
    return {
        'total_considered_users': total_considered_users,
        'total_unconsidered_users': total_unconsidered_users,
        'scores_cleaned': count_cleaned_scores,
        'progress': 0,
        'state': 'finished'
    }
