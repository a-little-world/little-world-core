from django.test import TestCase
from rest_framework.test import RequestsClient
import json
from rest_framework.response import Response
from django.conf import settings
from management.models import profile
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


class ChangePasswordTests(TestCase):

    def test_password_change_via_api(self):
        pass  # TODO!


class ChangeEmailTests(TestCase):

    def test_email_change(self):
        pass  # TODO!
