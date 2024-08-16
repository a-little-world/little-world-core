from django.test import TestCase
from rest_framework.test import RequestsClient
import os
import json
from rest_framework.response import Response
from management.tests.helpers import register_user, register_user_api
from management.controller import create_user, get_user_by_email, match_users
from management.api.user_data import get_user_models
from django.conf import settings
from rest_framework.test import APIRequestFactory, force_authenticate
from management.controller import match_users
from management.models.rooms import get_rooms_match
from management import api

valid_request_data = dict(
    email='benjamin.tim@gmx.de',
    first_name='Tim',
    second_name='Schupp',
    password1='Test123!',
    password2='Test123!',
    birth_year=1984
)

valid_create_data = dict(
    email=valid_request_data['email'],
    password=valid_request_data['password1'],
    first_name=valid_request_data['first_name'],
    second_name=valid_request_data['second_name'],
    birth_year=valid_request_data['birth_year'],
)


def _is_on_ci():
    return 'CI' in os.environ and os.environ['CI'].lower() in ('true', '1', 't')


class CallRoomTests(TestCase):

    required_params = api.register.Register.required_args

    def create_two_users_match(self):
        datas = [valid_request_data.copy(), valid_request_data.copy()]
        datas[1]["email"] = "benjamin1.tim@gmx.de"

        usrs = []
        for d in datas:
            response = register_user_api(d)
            assert response.status_code == 200
            usr = get_user_by_email(d["email"])
            usrs.append(usr)
        match_users({usrs[0], usrs[1]})
        return usrs[0], usrs[1]

    def test_video_room_creation(self):
        usrs = self.create_two_users_match()
        rooms = get_rooms_match(usrs[0], usrs[1])
        assert rooms.count() == 1

    # def test_authenticate_call(self): TODO
