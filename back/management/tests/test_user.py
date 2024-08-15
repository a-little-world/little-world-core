from django.test import TestCase
from rest_framework.test import RequestsClient
import json
from rest_framework.response import Response
from django.conf import settings
from management.models import profile
from rest_framework.test import APIRequestFactory, force_authenticate
from .. import api

class ChangePasswordTests(TestCase):

    def test_password_change_via_api(self):
        pass  # TODO!

class ChangeEmailTests(TestCase):

    def test_email_change(self):
        pass  # TODO!
