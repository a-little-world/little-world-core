import networkx as nx  # Tim loves graphs and networks and this is heck of a lib for it
import numpy as np  # Tim likes math too but graphs are even cooler
from ..models import Profile
from .score_tables import (
    helping_group,
    helping_group_msg,
    language_level,
    language_level_msg,
    partner_location,
    partner_location_msg
)


def _generate_table_scoring(
    usr1,
    usr2,
    # 'limiting_condition' should be a simple lambda function that takes a user
    # e.g.: lambda a : a.user_type == Profile.TypeChoices.VOLUNTEER
    # Note this *must* be wrong for one user and true for the other!
    limiting_condition,
    value_lookup,  # A lambda function that lookup the value of that field for both users
    table,  # The table containing integer scores, table should be 'numpy.array'!
    table_msgs=None  # A optional table containing messages
):
    """
    This function can be used for all scores that are based on some conditon that is different for both users
    Most notably this is 'learner vs volunteer' these scores are based on some table input.
    e.g.: helping_group, condition field 'user_type'
    | v/l |  0 |  1 |  2 | 3  |
    |:---:|:--:|:--:|:--:|----|
    |  0  | 25 | 30 | 20 | 20 |
    |  1  |  0 | 25 |  0 | 0  |
    |  2  | 0  | 0  | 25 | 0  |
    |  3  | 0  | 0  | 0  | 25 | 
    In this case the index correspond to the field 'profile.helping_group' 
    and the limiting condition is 'volunter or helper'
    condition 'True' always maps to y-axis
    condition 'False' always maps to x-axis
    if you wan't it otherwise yust negate the condition ;)
    """
    usrs = [usr1, usr2]
    cond = [limiting_condition(usr1), limiting_condition(usr2)]
    assert any(cond), "This condition is not exclusive"
    # [x, y] maps to the index of usrs:
    # e.g.: If cond is true for usr1 then y-axis maps to usr1, so we have to set [1, 0] -> [x, y]
    axes = [cond.index(False), cond.index(True)]

    # Check which values those people have set for the specific field
    values = [value_lookup(usr1), value_lookup(usr2)]

    # Now convert the numpy array to a graph
    graph = nx.from_numpy_matrix(table, create_using=nx.MultiGraph)
    text_graph = None
    if table_msgs:
        text_graph = nx.from_numpy_matrix(
            table_msgs, create_using=nx.MultiGraph)

    _matchable = True
    _usr1_to_usr2_score = graph[values[axes[0]]][values[axes[1]]][0]['weight']
    # This is mostry an integer but it can also be 'X' which would mean they are unmatchable!
    if _usr1_to_usr2_score.lower() == "x":
        _matchable = False
    else:
        # above is the only non integer case that is allowed
        # so it if wher not an integer we should error here:
        _usr1_to_usr2_score = int(_usr1_to_usr2_score)

    _msg = text_graph[values[axes[0]]][values[axes[1]]
                                       ][0]['weight'] if text_graph else None
    # Always return a tripel ( is_matchable, score, score message )
    return _matchable, _usr1_to_usr2_score, _msg


def dispatch_table_score(limiting_condition, value_lookup, table, table_msgs):
    # This is a wrapper that converts a table score function
    # in a function that only need usr1, usr2 as input
    # So basicly it sores the limiting conditon and the tables
    def run(usr1, usr2):
        return _generate_table_scoring(
            usr1, usr2, limiting_condition, value_lookup, table, table_msgs)
    return run


# Some reusable limiting conditions
LIMITING_CONDITIONS = dict(
    learner=lambda usr: usr.profile.user_type == Profile.TypeChoices.VOLUNTEER,
)


"""
This holds all the scoring functions,
per default they are *all* directional!
But there are some helpers you can use if you want to define a symetrical score
e.g.: _generate_table_scoring()
"""
SCORINGS = dict(  # These nice python 3 dicts are ordered! so this also defines the order of calcuation

    helping_group=dispatch_table_score(
        limiting_condition=LIMITING_CONDITIONS['learner'],
        value_lookup=lambda usr: usr.profile.user_type,
        table=helping_group,
        table_msgs=helping_group_msg),

    language_level=dispatch_table_score(
        limiting_condition=LIMITING_CONDITIONS['learner'],
        value_lookup=lambda usr: usr.profile.lang_level,
        table=language_level,
        table_msgs=language_level_msg),

    partner_location=dispatch_table_score(
        limiting_condition=LIMITING_CONDITIONS['learner'],
        value_lookup=lambda usr: usr.profile.partner_location,
        table=partner_location,
        table_msgs=partner_location_msg),

    # TODO: insert the other scorings ...
)


def calculate_directional_matching_score(
    usr1, usr2,
    return_on_nomatch=False
):
    """
    A general function that can calucate the directionmal matching score for two users 
    This is held very generic, and based on aboves SCORINGS dict
    we alsoways wan't to keep this rather abstract so we can easily modify this in the future

    Always returns a tripel: (matchable, total_score, messages)
    """
    _messages = {}  # Messenges will always be indexed by field name!
    _score = 0
    _matchable = True
    for scoring in SCORINGS:
        matchable, score, msg = SCORINGS[scoring](usr1, usr2)
        if not matchable:
            _matchable = False
        _score += score
        _messages[scoring] = msg if msg else "no message"
        if return_on_nomatch and not _matchable:
            return _matchable, _score, _messages
    # Incase you set return_on_nomatch=False,
    # you will get the full summary even if they are not matchable!
    return _matchable, _score, _messages
