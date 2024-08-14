from django.test import TestCase
from rest_framework.test import RequestsClient
import json
from rest_framework.response import Response
from management.controller import create_user, get_user_by_email, match_users
from management.api.user_data import get_user_models
from django.conf import settings
from rest_framework.test import APIRequestFactory, force_authenticate
from .. import api

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


class AdminApiTests(TestCase):
    def _create_abunch_of_users(self, amnt=20):
        mail_count = 0
        mail_fragments = valid_create_data["email"].split("@")

        def _make_mail(count):
            count += 1
            return count, mail_fragments[0] + str(count) + "@" + mail_fragments[1]

        users = []
        for i in range(amnt):
            # 20 test users
            _data = valid_create_data.copy()
            mail_count, _mail = _make_mail(mail_count)
            print(f"Creating user: '{_mail}'")
            _data['email'] = _mail
            users.append(create_user(**_data))
        return users

    def _match_all(self, users):
        # Matches *all* user in the users list
        stack = users.copy()
        while len(stack) > 1:
            usr = stack.pop(len(stack))  # begin at the highest index
            for _usr in stack:
                match_users({usr, _usr})

    def test_management_user_created(self):
        # Would throw error if users cant be created or
        # If the admin user doesn't yet exist
        # TODO: this looks broken @tbscode
        users = self._create_abunch_of_users(amnt=4)
        for u in users:
            assert u.state.matches

    def test_matches_made(self):
        users = self._create_abunch_of_users(amnt=20)
        for usr in users:
            get_user_models(usr)["state"].matches

    def test_user_list(self):
        pass
