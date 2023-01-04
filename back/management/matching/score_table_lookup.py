from dataclasses import dataclass
from typing import Callable, Optional, Union
from ..models import Profile

TARGET_GROUP_SCORES: str = r"""
| y:volunteer, x:learner | any.ler | refugee.ler | student.ler | worker.ler  |
|:----------------------:|:-------:|:-----------:|:-----------:|:-----------:|
| any.vol                |  25     |  30         |  20         |   20        |
| refugee.vol            |   0     |  25         |   0         |    0        |
| student.vol            |   0     |   0         |  25         |    0        |
| worker.vol             |   0     |   0         |   0         |   25        |
"""

TARGET_GROUP_MESSAGES: str = r"""
| y:volunteer, x:learner | any.ler | refugee.ler | student.ler | worker.ler  |
|:----------------------:|:-------:|:-----------:|:-----------:|:-----------:|
| any.vol                | both:any| v:any       | v:any       | v:any       |
| refugee.vol            |  -      | matching    |  -          |  -          |
| student.vol            |  -      |  -          | matching    |  -          |
| worker.vol             |  -      |  -          |  -          | matching    |
"""

PARTNER_LOCATION_SCORES: str = r"""
| y:volunteer, x:learner | anywhere.ler | close.ler | far.ler |
|:----------------------:|:------------:|:---------:|:-------:|
| anywhere.vol           |   5          |  15       |  10     |
| close.vol              |  15          |  20       |  X      |
| far.vol                |  10          |  X        |  20     |
"""

LANGUAGE_LEVEL_SCORES: str = r"""
| y:volunteer, x:learner | level-0.ler | level-1.ler | level-2.ler | level-3.ler |
|:----------------------:|:-----------:|:-----------:|:-----------:|:-----------:|
| level-0.vol            |  30         |  20         |  15         |  10         |
| level-1.vol            |  0          |  30         |  20         |  15         |
| level-2.vol            |  0          |  0          |  30         |  20         |
| level-3.vol            |  0          |  0          |  0          |  30         |
"""


def __profile_choice_by_user_type(choice):
    """
    This basically removes the .vol or .ler from the choice
    also asserts that the choice is valid
    """
    ends = [".vol", ".ler"]
    assert any([choice.endswith(c) for c in ends])
    # TODO: somehow catch if dev accidently retused
    # .ler / .vol in profile choice
    return choice.replace(".vol", "").replace(".ler", "")


MIN_POSTAL_CODE_DISTANCE = 3000


def check__plz_distance_matching_score(usr1, usr2):
    """
    Checks dependant on partner location choice the PLZ area distance
    """
    ptc = __profile_choice_by_user_type
    meta = {}
    msg = ""
    if usr1.profile.partner_location == ptc(Profile.ConversationPartlerLocation.CLOSE_VOL):
        msg += "This user looks for a close match!" + "\n"
        # check if the postal_code is set
        if usr1.profile.postal_code and usr2.profile.postal_code:
            msg += "Both users have a postal code set!" + "\n"
            postal_code1 = int(usr1.profile.postal_code)
            postal_code2 = int(usr2.profile.postal_code)
            meta = {"values": (postal_code1, postal_code2)}
            # check if the postal_code is close
            if postal_code1 - postal_code2 < MIN_POSTAL_CODE_DISTANCE:
                msg += "Both users have a close postal code!" + "\n"
                return True, 50, msg, meta
            else:
                msg += "users have a far postal code!" + "\n"
                return False, 0, msg, meta
        else:
            return False, 0, "At least one user doesn't have a postal code set!" + "\n" \
                + "But user has requested close, so setting 'unmatchable'"
    return True, 0, "User hasn't selected close, nothing to check", meta


def check__volunteer_vs_learner(usr1, usr2):
    oppsite = any([usr1.profile.user_type == Profile.TypeChoices.LEARNER and usr2.profile.user_type ==
                   Profile.TypeChoices.VOLUNTEER,
                   usr1.profile.user_type == Profile.TypeChoices.VOLUNTEER and usr2.profile.user_type ==
                   Profile.TypeChoices.LEARNER])
    return oppsite, 0, "Learner and Volunteer!" if oppsite else "Can't match both either learner or volunteer", {"values": (usr1.profile.user_type, usr2.profile.user_type)}


def check__time_slot_overlap(usr1, usr2):
    """
    Calculate overlapping time slots 
    We assigns some scores for overlapping interests
    But this can never cause 'unmatchable'
    """
    from ..validators import DAYS, SLOTS
    slots1 = usr1.profile.availability
    slots2 = usr2.profile.availability

    BASE_SCORES = [-15, 15, 25, 29, 32, 35, 37]
    amnt_common_slots = 0
    common_slots = {}

    for day in DAYS:
        for slot in SLOTS:
            if day in slots1 and day in slots2 and slot in slots1[day] and slot in slots2[day]:
                common_slots[day] = common_slots.get(day, []) + [slot]
                amnt_common_slots += 1

    return True, BASE_SCORES[amnt_common_slots] if amnt_common_slots < len(BASE_SCORES) else BASE_SCORES[len(BASE_SCORES)-1], \
        "Common slots: " + str(common_slots), \
        {"values": (slots1, slots2), "common_slots": common_slots}


def check__interest_overlap(usr1, usr2):
    """
    Calculate overlapping interests
    also can nv cause 'unmatchable'
    """
    it1 = usr1.profile.interests
    it2 = usr2.profile.interests
    MAX_SCORE = 30
    SCORE_STEP = 5

    common_interests = set(it1).intersection(set(it2))
    score = SCORE_STEP * len(common_interests)

    return True, score if score < MAX_SCORE else MAX_SCORE, \
        "Common interests: " + str(common_interests) + \
        (f". Score was capped at {MAX_SCORE} per default" if score > MAX_SCORE else ""), \
        {"values": (it1, it2), "common_interests": list(common_interests)}


def load_or_predict_gender_with_gender_api(usr):
    if not usr.profile.gender_prediction:
        raise Exception("Generder api key needs updating!")
        gender_api_key = "Y6aBX6Jg3QpnzaGSefg7Y9VPsY9jzH6PzwRW"
        _url = "https://gender-api.com/v2/gender/by-full-name"
        request_data = {
            "full_name": f"{usr.profile.first_name} {usr.profile.second_name}",
        }
        import requests
        headers = {"Authorization": f"Bearer {gender_api_key}"}

        prediction = requests.post(
            _url, data=request_data, headers=headers).json()

        usr.profile.gender_prediction = prediction
        usr.profile.save()
    return usr.profile.gender_prediction


def check__partner_sex_choice(usr1, usr2):
    """
    Checks if the match gender preference is met
    NOTE this is currently no definaive programmatic process
    This just predicts the gender via gender api
    """
    from ..models import Profile

    c1 = usr1.profile.partner_sex
    c2 = usr2.profile.partner_sex

    p1 = load_or_predict_gender_with_gender_api(usr1)
    p2 = load_or_predict_gender_with_gender_api(usr2)

    return True, 0, f"usr1({usr1.email}) wants {c1}. usr2({usr2.email}) wants {c2}\n" + \
        f"For usr1({usr1.email} we predict {p1}. For usr2({usr2.email}) we predict {p2}",  \
        {"values": (c1, c2), "gender_predictions": (p1, p2)}
