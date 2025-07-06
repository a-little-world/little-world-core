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

- [ ] How to Communicate ( checkId: `speech_medium` )
> this considers `profile.speech_medium`
if `user.speech_medium === other.speech_medium` then `+ 40 score`
if `user.speech_medium.VIDEO and other.speech_medium is AUDIO` then `-> unmatchable`
if `user.speech_medium.ANY and other.speech_medium is AUDIO` then `-> unmatchable`
Last one is a little try and caused some users to have very limited options in the past

"""

import dataclasses
import itertools
import json
import math
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

import pgeocode
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer

from back.utils import CoolerJson
from management import controller
from management.api.user_advanced_filter import needs_matching
from management.helpers import IsAdminOrMatchingUser
from management.models.matches import Match
from management.models.profile import Profile
from management.models.scores import TwoUserMatchingScore
from management.models.state import State
from management.models.unconfirmed_matches import ProposedMatch
from management.models.user import User
from management.tasks import burst_calculate_matching_scores, matching_algo_v2
from management.validators import DAYS, SLOTS
from management.utils import check_task_status


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

    def dict(self):
        return dataclasses.asdict(self)


class ScoringFunctionsEnum(Enum):
    language_level = "language_level"
    learner_vs_volunteer = "learner_vs_volunteer"
    time_slot_overlap = "time_slot_overlap"
    postal_code_distance = "postal_code_distance"
    gender = "gender"
    interest_overlap = "interest_overlap"
    speech_medium = "speech_medium"
    already_matched_or_proposed = "already_matched_or_proposed"
    learner_no_match_bonus = "learner_no_match_bonus"
    match_in_past = "match_in_past"
    target_group = "target_group"


class ScoringBase:
    def __init__(
        self,
        user1,
        user2,
    ) -> None:
        self.user1 = user1
        self.user2 = user2
        # register scoring functions
        self.scoring_fuctions = {
            ScoringFunctionsEnum.language_level.value: self.score__language_level,
            ScoringFunctionsEnum.learner_vs_volunteer.value: self.score__volunteer_vs_learner,
            ScoringFunctionsEnum.time_slot_overlap.value: self.score__time_slot_overlap,
            ScoringFunctionsEnum.postal_code_distance.value: self.score__postal_code_distance,
            ScoringFunctionsEnum.gender.value: self.score__gender,
            ScoringFunctionsEnum.interest_overlap.value: self.score__interest_overlap,
            # ScoringFunctionsEnum.speech_medium.value: self.score__speech_medium, # Disabled atm ( team meeting decision Sep 2024 )
            ScoringFunctionsEnum.already_matched_or_proposed.value: self.score__already_matched_or_proposed,
            ScoringFunctionsEnum.learner_no_match_bonus.value: self.score__learner_no_match_bonus,
            ScoringFunctionsEnum.match_in_past.value: self.score__reported_or_unmatched_in_past,
            ScoringFunctionsEnum.target_group.value: self.score__target_group,
        }

    def score__time_slot_overlap(self):
        """
        Table based scores amount overlaps
        `{"<=0": -15, "=1: 15, "=2": 25, "=3": 29, "=4": 32, "=5": 35, ">=6": 37}
        """
        slots1 = self.user1.profile.availability
        slots2 = self.user2.profile.availability

        amnt_common_slots = 0
        common_slots = {}

        for day in DAYS:
            for slot in SLOTS:
                if day in slots1 and day in slots2 and slot in slots1[day] and slot in slots2[day]:
                    common_slots[day] = common_slots.get(day, []) + [slot]
                    amnt_common_slots += 1
        conditions = [
            [lambda x: x <= 0, -15],
            [lambda x: x == 1, 15],
            [lambda x: x == 2, 25],
            [lambda x: x == 3, 29],
            [lambda x: x == 4, 32],
            [lambda x: x == 5, 35],
            [lambda x: x >= 6, 37],
        ]
        for cond in conditions:
            if cond[0](amnt_common_slots):
                return ScoringFuctionResult(
                    matchable=True,
                    score=cond[1],
                    weight=1.0,
                    markdown_info=f"Common slots: ({str(amnt_common_slots)}) {str(common_slots)} (score: {cond[1]})",
                )
        return ScoringFuctionResult(
            matchable=True,
            score=0,
            weight=1.0,
            markdown_info=f"Common slots: ({str(amnt_common_slots)}) {str(common_slots)} (score: 0)",
        )

    def score__volunteer_vs_learner(self):
        """
        Simple chat the we match only volunteers and learners!
        """
        oppsite = any(
            [
                self.user1.profile.user_type == Profile.TypeChoices.LEARNER
                and self.user2.profile.user_type == Profile.TypeChoices.VOLUNTEER,
                self.user1.profile.user_type == Profile.TypeChoices.VOLUNTEER
                and self.user2.profile.user_type == Profile.TypeChoices.LEARNER,
            ]
        )
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
            return ScoringFuctionResult(
                matchable=False,
                score=0,
                weight=1.0,
                markdown_info="Volunteer has a higher min lang level than learner (score: 0)",
            )
        else:
            return ScoringFuctionResult(
                matchable=True,
                score=30,
                weight=1.0,
                markdown_info="Volunteer has a lower min lang level than learner (score: 5)",
            )

    def score__postal_code_distance(self):
        """
        Checks dependant on partner location choice the PLZ area distance
        `{"<50": 50, "<100": 40, "<200": 30, "<300": 20, "<400": 10, "<500": 5, ">500": 0}`
        """

        dist = pgeocode.GeoDistance("de")
        distance = dist.query_postal_code(self.user1.profile.postal_code, self.user2.profile.postal_code)
        conditions = [
            [lambda x: x < 50.0, 18.0],
            [lambda x: x < 100.0, 16.0],
            [lambda x: x < 200.0, 14.0],
            [lambda x: x < 300.0, 12.0],
            [lambda x: x < 400.0, 10.0],
            [lambda x: x < 500.0, 5.0],
            [lambda x: x >= 500.0, 0.0],
        ]
        for cond in conditions:
            if cond[0](distance):
                return ScoringFuctionResult(
                    matchable=True,
                    score=cond[1],
                    weight=1.0,
                    markdown_info=f"Distance is {distance}km (score: {cond[1]})",
                )
        return ScoringFuctionResult(
            matchable=True, score=0, weight=1.0, markdown_info=f"Distance is {distance}km (score: 0)"
        )

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
            Profile.GenderChoices.DIVERSE: "diverse",
            Profile.PartnerGenderChoices.ANY: "any",
            Profile.PartnerGenderChoices.FEMALE: "female",
            Profile.PartnerGenderChoices.MALE: "male",
            Profile.PartnerGenderChoices.DIVERSE: "diverse",
            None: "any",
        }

        def male_or_female_or_diverse(gender):
            return (gender == "male") or (gender == "female") or (gender == "diverse")

        def wish_granted(gender, wish):
            granted = gender == wish
            still_ok = granted or (wish == "any")
            return granted, still_ok

        gender1 = normalize_gender_choices[self.user1.profile.gender]
        partner_gender1 = normalize_gender_choices[self.user1.profile.partner_gender]
        gender2 = normalize_gender_choices[self.user2.profile.gender]
        partner_gender2 = normalize_gender_choices[self.user2.profile.partner_gender]

        # disallow when any gender wish is broken:
        # e.g.: wish = "male" -> other = "female", but also wish = "female" -> other = "any"
        if (male_or_female_or_diverse(partner_gender1) and gender2 == "any") or (
            male_or_female_or_diverse(partner_gender2) and gender1 == "any"
        ):
            return ScoringFuctionResult(
                matchable=False,
                score=0,
                weight=1.0,
                markdown_info="Wish for specific gender cannot be fulfilled since partner has 'any' gender",
            )

        wish1, sok1 = wish_granted(gender1, partner_gender2)
        wish2, sok2 = wish_granted(gender2, partner_gender1)
        # all get exatly what they wish for
        if wish1 and wish2:
            return ScoringFuctionResult(
                matchable=True,
                score=20.0,
                weight=1.0,
                markdown_info="All gender requests presisely fullfilled :white_check_mark: (score: 20)",
            )

        if sok1 and sok2:
            return ScoringFuctionResult(
                matchable=True, score=10.0, weight=1.0, markdown_info="All gender choices ok, some 'any' (score: 10.0)"
            )

        return ScoringFuctionResult(
            matchable=False,
            score=0.0,
            weight=1.0,
            markdown_info=f"Gender reuests chant be fullfilled (g:{gender1},w:{partner_gender1})<->(g:{gender2},w:{partner_gender2})",
        )

    def score__interest_overlap(self):
        """
        We assigns some scores for overlapping interests
        But this can never cause 'unmatchable'
        """

        it1 = self.user1.profile.interests
        it2 = self.user2.profile.interests

        common_interests = set(it1).intersection(set(it2))
        amnt_common_interests = len(common_interests)

        conditions = [
            [lambda x: x == 0, 0],
            [lambda x: x == 1, 5],
            [lambda x: x == 2, 10],
            [lambda x: x == 3, 15],
            [lambda x: x == 4, 20],
            [lambda x: x == 5, 25],
            [lambda x: x >= 6, 30],
        ]

        for cond in conditions:
            if cond[0](amnt_common_interests):
                return ScoringFuctionResult(
                    matchable=True,
                    score=cond[1],
                    weight=1.0,
                    markdown_info=f"Interests Overlap: {str(common_interests)} (score: {cond[1]})",
                )

        return ScoringFuctionResult(matchable=True, score=0, weight=1.0, markdown_info="Interests Overlap (score: 0)")

    def score__learner_no_match_bonus(self):
        learner_user = self.user1 if self.user1.profile.user_type == Profile.TypeChoices.LEARNER else self.user2
        learner_has_no_match_yet = (
            Match.objects.filter(Q(user1=learner_user) | Q(user2=learner_user), support_matching=False).count() == 0
        )
        # We deliberately don't require active=True, as we don't wanna give the bonus to people that resolved their match
        if learner_has_no_match_yet:
            return ScoringFuctionResult(
                matchable=True,
                score=20,
                weight=1.0,
                markdown_info=f"Learner has no match yet: {learner_has_no_match_yet} (score: 20)",
            )
        return ScoringFuctionResult(
            matchable=True,
            score=0,
            weight=1.0,
            markdown_info=f"Learner has no match yet: {learner_has_no_match_yet} (score: 0)",
        )

    def score__speech_medium(self):
        speech_medium1 = self.user1.profile.speech_medium
        speech_medium2 = self.user2.profile.speech_medium

        if (
            speech_medium1 == Profile.SpeechMediumChoices2.ANY
            and (
                speech_medium2 == Profile.SpeechMediumChoices2.PHONE
                or speech_medium2 == Profile.SpeechMediumChoices2.VIDEO
            )
        ) or (
            speech_medium2 == Profile.SpeechMediumChoices2.ANY
            and (
                speech_medium1 == Profile.SpeechMediumChoices2.PHONE
                or speech_medium1 == Profile.SpeechMediumChoices2.VIDEO
            )
        ):
            return ScoringFuctionResult(
                matchable=True, score=10, weight=1.0, markdown_info="Speech Medium: Any  :white_check_mark: (score: 10)"
            )
        if speech_medium1 == speech_medium2:
            return ScoringFuctionResult(
                matchable=True,
                score=40,
                weight=1.0,
                markdown_info=f"Speech Medium: {speech_medium1} requested :white_check_mark: (score: 40)",
            )

        return ScoringFuctionResult(
            matchable=False,
            score=0,
            weight=1.0,
            markdown_info=f"Speech Medium: {speech_medium1} requested but {speech_medium2} offered :x: (score: 0)",
        )

    def score__already_matched_or_proposed(self):
        mutal_proposed_match = ProposedMatch.objects.filter(
            Q(user1=self.user1, user2=self.user2) | Q(user1=self.user2, user2=self.user1), closed=False
        )
        mutal_match = Match.objects.filter(
            Q(user1=self.user1, user2=self.user2) | Q(user1=self.user2, user2=self.user1), active=True
        )
        has_mutal_proposed_or_regular_match = mutal_proposed_match.exists() or mutal_match.exists()

        return ScoringFuctionResult(
            matchable=not has_mutal_proposed_or_regular_match,
            score=0,
            weight=1.0,
            markdown_info=f"Already matched or proposed: {has_mutal_proposed_or_regular_match} :x: (score: 0)",
        )

    def score__reported_or_unmatched_in_past(self):
        mutal_past_match = Match.objects.filter(
            Q(user1=self.user1, user2=self.user2) | Q(user1=self.user2, user2=self.user1), active=False
        )
        mutal_past_match_exists = mutal_past_match.exists()

        if mutal_past_match_exists:
            return ScoringFuctionResult(
                matchable=False,
                score=0,
                weight=1.0,
                markdown_info=f"Have been matched in the past & was reported or unmatched: {mutal_past_match_exists} :x: (score: 0)",
            )
        return ScoringFuctionResult(
            matchable=True,
            score=0,
            weight=1.0,
            markdown_info=f"Never been matched in the past / never was reported or unmatched: {mutal_past_match_exists} :white_check_mark: (score: 0)",
        )

    def score__target_group(self):
        """
        Checks if the target group preferences match between volunteer and learner.

        Hybrid approach:
        - If volunteer specifically requests refugees but learner isn't a refugee -> unmatchable
        - Otherwise, add positive scoring for matching target groups
        """
        volunteer = self.user1 if self.user1.profile.user_type == Profile.TypeChoices.VOLUNTEER else self.user2
        learner = self.user1 if self.user1.profile.user_type == Profile.TypeChoices.LEARNER else self.user2

        volunteer_target_group = volunteer.profile.target_group
        learner_target_groups = learner.profile.target_groups

        # If learner hasn't specified any target groups, use the single target_group field
        if not learner_target_groups:
            learner_target_groups = [learner.profile.target_group]

        # Case 1: Volunteer specifically requests refugees
        if volunteer_target_group == Profile.TargetGroupChoices2.REFUGEE:
            if Profile.TargetGroupChoices2.REFUGEE not in learner_target_groups:
                return ScoringFuctionResult(
                    matchable=False,
                    score=0,
                    weight=1.0,
                    markdown_info="Volunteer specifically requested refugees, but learner is not a refugee (unmatchable)",
                )
            else:
                return ScoringFuctionResult(
                    matchable=True,
                    score=30,
                    weight=1.0,
                    markdown_info="Volunteer requested refugees and learner is a refugee (score: 30)",
                )

        # Case 2: Volunteer requests any specific target group (not ANY)
        if volunteer_target_group != Profile.TargetGroupChoices2.ANY:
            if volunteer_target_group in learner_target_groups:
                return ScoringFuctionResult(
                    matchable=True,
                    score=20,
                    weight=1.0,
                    markdown_info=f"Volunteer requested {volunteer_target_group} and learner belongs to this group (score: 20)",
                )
            else:
                return ScoringFuctionResult(
                    matchable=True,
                    score=-20,
                    weight=1.0,
                    markdown_info=f"Volunteer requested {volunteer_target_group} but learner doesn't belong to this group (score: -20)",
                )

        # Case 3: Volunteer is fine with any target group
        return ScoringFuctionResult(
            matchable=True,
            score=5,
            weight=1.0,
            markdown_info="Volunteer is fine with any target group (score: 5)",
        )

    def calculate_score(self, raise_exception=False):
        results = []
        error_occured = False
        for score_function in list(self.scoring_fuctions.keys()):
            try:
                res = self.scoring_fuctions[score_function]()
                assert res, f"Score function must return a ScoringFuctionResult: {score_function} doesn't"
            except Exception as e:
                error_occured = True
                print(f"Error in score function {score_function}:", e)
                if raise_exception:
                    raise e
                res = ScoringFuctionResult(
                    matchable=False, score=0, weight=1.0, markdown_info=f"ERROR in score function {score_function}: {e}"
                )
            results.append({"score_function": score_function, "res": res.dict()})

        total_score = sum([res["res"]["score"] * res["res"]["weight"] for res in results])
        matchable = all([res["res"]["matchable"] for res in results])
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


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def dispatch_score_calculation(request):
    assert request.user.is_staff or request.user.state.has_extra_user_permission(
        State.ExtraUserPermissionChoices.MATCHING_USER
    )

    serializer = DispatchScoreCalculationSerializer(request.data)
    serializers.is_valid(raise_exception=True)
    data = serializer.save()

    task = matching_algo_v2.delay(data["user"], 50)

    return Response(
        {
            "msg": "Task dispatched scores will be written to db on task completion",
            "task_id": task.task_id,
            "view": f"/admin/django_celery_results/taskresult/?q={task.task_id}",
        }
    )


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def calculate_score_between(request):
    serializer = ScoreBetweenDataclass(request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.data

    user1 = User.objects.get(id=data["user1"])
    user2 = User.objects.get(id=data["user2"])

    total_score, matchable, results = score_between_db_update(user1, user2)
    return Response({"total_score": total_score, "matchable": matchable, "results": results})


def get_users_to_consider(usr=None, consider_only_registered_within_last_x_days=None, exlude_user_ids=[]):
    all_users_to_consider = (
        User.objects.annotate(
            has_open_proposal=Exists(
                ProposedMatch.objects.filter(Q(user1=OuterRef("pk")) | Q(user2=OuterRef("pk")), closed=False)
            )
        )
        .filter(
            state__searching_state=State.SearchingStateChoices.SEARCHING,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__had_prematching_call=True,
            state__email_authenticated=True,
            is_staff=False,
            has_open_proposal=False,
        )
        .exclude(state__user_category__in=[State.UserCategoryChoices.SPAM, State.UserCategoryChoices.TEST])
    )

    if len(exlude_user_ids) > 0:
        all_users_to_consider = all_users_to_consider.exclude(pk__in=exlude_user_ids)

    if usr is not None:
        all_users_to_consider = all_users_to_consider.exclude(pk=usr.pk)

    if consider_only_registered_within_last_x_days is not None:
        from django.utils import timezone

        today = timezone.now()
        x_days_ago = today - timedelta(days=consider_only_registered_within_last_x_days)
        all_users_to_consider = all_users_to_consider.filter(date_joined__gte=x_days_ago)

    return all_users_to_consider


def calculate_scores_user(
    user_pk, consider_only_registered_within_last_x_days=None, report=lambda data: print(data), exlude_user_ids=[]
):
    from django.db.models import Exists, OuterRef, Q

    from management import controller

    usr = controller.get_user_by_pk(user_pk)

    all_users_to_consider = get_users_to_consider(usr, consider_only_registered_within_last_x_days, exlude_user_ids)

    # - We have to set the score of all users not to consider to 0
    all_users_not_to_consider = User.objects.annotate(
        to_consider=Exists(all_users_to_consider.filter(pk=OuterRef("id")))
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

    matchable_count = 0
    c = 0
    report(
        {
            "total_considered_users": total_considered_users,
            "total_unconsidered_users": total_unconsidered_users,
            "scores_cleaned": count_cleaned_scores,
            "progress": 0,
            "matchable_count": matchable_count,
            "state": "starting",
        }
    )

    for user in all_users_to_consider:
        c += 1
        total_score, matchable, results, score = score_between_db_update(usr, user)

        if matchable:
            matchable_count += 1

        report(
            {
                "total_considered_users": total_considered_users,
                "total_unconsidered_users": total_unconsidered_users,
                "scores_cleaned": count_cleaned_scores,
                "progress": c,
                "matchable_count": matchable_count,
                "state": "processing",
                "current_user": user.pk,
            }
        )

    return {
        "total_considered_users": total_considered_users,
        "total_unconsidered_users": total_unconsidered_users,
        "scores_cleaned": count_cleaned_scores,
        "matchable_count": matchable_count,
        "progress": c,
        "state": "finished",
    }


@dataclass
class SimplePagination:
    page: int
    items_per_page: int
    total_pages: int
    total_items: int
    results: list

    def dict(self):
        return self.__dict__.copy()


from management.models import scores


class SimpleMatchingScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = scores.TwoUserMatchingScore
        fields = ["id", "user1", "user2", "score"]


class BurstCalculateMatchingScoresV2RequestSerializer(serializers.Serializer):
    parallel_tasks = serializers.IntegerField(
        help_text="The number of parallel tasks to run", default=4, required=False
    )
    delete_old_scores = serializers.BooleanField(
        help_text="Delete all old scores before starting", default=True, required=False
    )


@extend_schema(
    request=BurstCalculateMatchingScoresV2RequestSerializer,
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def burst_calculate_matching_scores_v2(request):
    from management.models.backend_state import BackendState

    ongoing_update = BackendState.objects.filter(slug=BackendState.BackendStateEnum.updating_matching_scores)

    if ongoing_update.exists():
        return Response({"msg": "Already updating scores"}, status=400)
    else:
        ongoing_update = BackendState.objects.create(
            slug=BackendState.BackendStateEnum.updating_matching_scores, meta={"tasks": []}
        )

    serializer = BurstCalculateMatchingScoresV2RequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    parallel_tasks = serializer.validated_data["parallel_tasks"]

    if serializer.validated_data["delete_old_scores"]:
        TwoUserMatchingScore.objects.all().delete()

    bmu = controller.get_base_management_user()
    requires_matching = needs_matching(qs=User.objects.filter(id__in=bmu.state.managed_users.all()), learner_atleast_searching_for_x_days=5)
    user_id_set = set(requires_matching.values_list("id", flat=True))
    list_combinations = list(itertools.combinations(user_id_set, 2))

    total_combinations = len(list_combinations)
    chunk_size = math.ceil(total_combinations / parallel_tasks)

    task_batches = [list_combinations[i : i + chunk_size] for i in range(0, total_combinations, chunk_size)]

    if not task_batches:
        return Response({"msg": "No matching needed"}, status=200)

    created_tasks = [burst_calculate_matching_scores.delay(batch) for batch in task_batches]

    created_tasks_ids = [task.id for task in created_tasks]

    ongoing_update.meta["tasks"] = created_tasks_ids
    ongoing_update.meta["completed_tasks"] = []
    ongoing_update.save()

    return Response(created_tasks_ids)


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def get_active_burst_calculation(request):
    from management.models.backend_state import BackendState

    ongoing_update = BackendState.objects.filter(slug=BackendState.BackendStateEnum.updating_matching_scores)

    if ongoing_update.exists():
        tasks = ongoing_update.first().meta["tasks"]
        task_states = [check_task_status(task_id) for task_id in tasks]

        return Response({"active": True, "tasks": task_states})
    else:
        return Response({"active": False})


def instantly_possible_matches():
    import networkx as nx

    from management.models.scores import TwoUserMatchingScore

    matches = SimpleMatchingScoreSerializer(
        TwoUserMatchingScore.objects.filter(matchable=True).order_by("-score"), many=True
    ).data

    G = nx.Graph()
    print("CONSIDERED", matches)

    # Add an edge for each pair of users with the score as weight
    for match in matches:
        G.add_edge(match["user1"], match["user2"], weight=float(match["score"]))

    # Use the max_weight_matching function of NetworkX
    matches = nx.max_weight_matching(G, maxcardinality=True)

    # max_weight_matching returns a set of frozensets, convert to list of tuples
    matches = [tuple(match) for match in matches]
    return matches


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def score_maximization_matching(request):
    from management.api.user_advanced import AdvancedMatchingScoreSerializer
    from management.models.scores import TwoUserMatchingScore

    matches = instantly_possible_matches()

    print("MATCHES", matches)

    # perform a finaly check if not users are matched twice
    user_pks = []
    for match in matches:
        if match[0] in user_pks or match[1] in user_pks:
            # Fow now if the user was already matched we just ignore that score
            pass
            # TODO: make ignoring this case optional
            # raise ValueError("User matched twice")
        else:
            user_pks.append(match[0])
            user_pks.append(match[1])

    items_per_page = int(request.query_params.get("items_per_page", 50))
    page = int(request.query_params.get("page", 1))

    scores = []
    for match in matches:
        user1 = User.objects.get(id=match[0])
        user2 = User.objects.get(id=match[1])
        score = TwoUserMatchingScore.get_score(user1, user2)
        scores.append(score)

    paginator = Paginator(scores, items_per_page)
    pages = paginator.page(page)
    serialized = [AdvancedMatchingScoreSerializer(p, many=False, context={"user": p.user1}).data for p in list(pages)]

    return Response(
        SimplePagination(
            page=page,
            items_per_page=items_per_page,
            total_pages=paginator.num_pages,
            total_items=len(scores),
            results=serialized,
        ).dict()
    )


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def delete_all_matching_scores(request):
    assert request.user.is_staff or request.user.state.has_extra_user_permission(
        State.ExtraUserPermissionChoices.MATCHING_USER
    )
    from management.models.scores import TwoUserMatchingScore

    total_count = TwoUserMatchingScore.objects.count()
    TwoUserMatchingScore.objects.all().delete()
    return Response({"msg": f"All {total_count} matching scores deleted"})


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def list_top_scores(request):
    assert request.user.is_staff or request.user.state.has_extra_user_permission(
        State.ExtraUserPermissionChoices.MATCHING_USER
    )
    from management.api.user_advanced import AdvancedMatchingScoreSerializer
    from management.models.scores import TwoUserMatchingScore

    top_scores = TwoUserMatchingScore.objects.filter(matchable=True).order_by("-score")

    items_per_page = int(request.query_params.get("items_per_page", 50))
    page = int(request.query_params.get("page", 1))

    paginator = Paginator(top_scores, items_per_page)
    pages = paginator.page(page)
    serialized = [AdvancedMatchingScoreSerializer(p, many=False, context={"user": p.user1}).data for p in list(pages)]

    return Response(
        SimplePagination(
            page=page,
            items_per_page=items_per_page,
            total_pages=paginator.num_pages,
            total_items=top_scores.count(),
            results=serialized,
        ).dict()
    )
