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
| anywhere.vol           |  40          |  X        |  25     |
| close.vol              |  X           |  15       |  10     |
| far.vol                |  25          |  10       |  5      |
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
                return True, 50, msg
            else:
                msg += "users have a far postal code!" + "\n"
                return False, 0, msg
        else:
            return False, 0, "At least one user doesn't have a postal code set!" + "\n" \
                + "But user has requested close, so setting 'unmatchable'"
    return True, 0, "User hasn't selected close, nothing to check", meta


def check__volunteer_vs_learner(usr1, usr2):
    oppsite = any([usr1.user_type == Profile.TypeChoices.LEARNER and usr2.user_type ==
                   Profile.TypeChoices.VOLUNTEER,
                   usr1.user_type == Profile.TypeChoices.VOLUNTEER and usr2.user_type ==
                   Profile.TypeChoices.LEARNER])
    return oppsite, 0, "Learner and Volunteer!" if oppsite else "Can't match both learner/volunteer", {}
