import json

from django.conf import settings
from django.test import TestCase
from rest_framework.test import RequestsClient

from management.api.user_advanced_filter_lists import USER_JOURNEY_FILTER_LISTS
from management.controller import get_user_by_email
from management.models.user import User
from management.tests.helpers import register_user, register_user_api, valid_register_request_data

from .. import api

BUCKETS = {
    "sign-up": [
        "journey_v2__user_created",
        "journey_v2__email_verified",
        "journey_v2__user_form_completed",
        "journey_v2__booked_onboarding_call",
        "journey_v2__first_search",
    ],
    "active-users": [
        "journey_v2__user_searching_again",
        "journey_v2__pre_matching",
        "journey_v2__match_takeoff",
        "journey_v2__active_matching",
    ],
}


def get_user_journey_list(list_name):
    for list in USER_JOURNEY_FILTER_LISTS:
        if list.name == list_name:
            return list

    return None


def test_local():
    singn_up = BUCKETS["active-users"]
    counts = {}
    values = {}

    for i in range(len(singn_up)):
        _list = get_user_journey_list(singn_up[i])
        values[singn_up[i]] = list(_list.queryset(User.objects.all()).values_list("id", flat=True))
        counts[singn_up[i]] = _list.queryset(User.objects.all()).count()

    print("CC", counts, values)
    print("Comparing", singn_up)

    for i in range(len(singn_up)):
        for j in range(i + 1, len(singn_up)):
            print("Comparing", singn_up[i], singn_up[j])
            list1 = set(
                list(get_user_journey_list(singn_up[i]).queryset(User.objects.all()).values_list("id", flat=True))
            )
            list2 = set(
                list(get_user_journey_list(singn_up[j]).queryset(User.objects.all()).values_list("id", flat=True))
            )
            # print("Comparing", list1, list2)
            # print("Comparing", list1.intersection(list2))
            intersection = list1.intersection(list2)
            if len(intersection) != 0:
                print("Dupricate ids in lists", intersection, "lists:", singn_up[i], singn_up[j])


class TestUserJourneyV2(TestCase):
    required_params = api.register.Register.required_args

    def test_list_duplications(self):
        # TODO: test depricated as it contains non-mysql compatibe lookups also it doesn't really make sense to run it without a large dataset
        # singn_up = BUCKETS['sign-up']
        # counts = {}
        # for i in range(len(singn_up)):
        #    _list = get_user_journey_list(singn_up[i])
        #    counts[singn_up[i]] = _list.queryset(User.objects.all()).count()
        # print("CC", counts)
        pass
