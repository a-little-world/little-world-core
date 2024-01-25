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
from enum import Enum
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
    unmatchable: bool
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
            scoring_functions_enabled = None,
            ) -> None:
        self.user1 = user1
        self.user2 = user2
        if scoring_functions_enabled is None:
            scoring_functions_enabled = self.get_all_scoring_function_names()
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
        return ScoringFuctionResult(matchable=(not oppsite), score=0, weight=1.0, markdown_info=msg)
    
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
        learner_german_level = learner.profile.lang_skill.filter(language="german").first().level
        
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
    
    def calculate_score(self):
        
        results = []
        for score_function in list(self.scoring_fuctions.keys()):
            try:
                res = self.scoring_fuctions[score_function]()
            except Exception as e:
                print(f"Error in score function {score_function}:", e)
                res = ScoringFuctionResult(matchable=False, score=0, weight=1.0, markdown_info=f"Error in score function {score_function}: {e}")
            results.append(res)
            
        total_score = sum([res.score * res.weight for res in results])
        matchable = all([res.matchable for res in results])
        return total_score, matchable, results

def score_between_db_update(user1, user2):
    base = ScoringBase(user1, user2)
    total_score, matchable, results = base.calculate_score()
    
    TwoUserMatchingScore.get_or_create(user1, user2).update(
        score=total_score,
        matchable=matchable,
        scoring_results=[dataclasses.asdict(r) for r in results]
    )
    
    # TODO: we could further gain memroy by not sotring unmatchable scores at all
    return total_score, matchable, results
    
    

@api_view(['POST'])
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
