from django.test import TestCase
from rest_framework.response import Response
from management.controller import create_user_matching_proposal
from rest_framework.test import APIRequestFactory, force_authenticate
from management.random_test_users import create_abunch_of_users, modify_profile_to_match
from management.models.profile import Profile
from management.tests.helpers import register_user

from management.models.unconfirmed_matches import get_unconfirmed_matches
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


class MatchConfirmationTasksTests(TestCase):

    required_params = api.register.Register.required_args

    def _some_confirm_deny_match_call(self, data: dict, user=None) -> Response:
        factory = APIRequestFactory(enforce_csrf_checks=True)

        request = factory.post('user/match/confirm_deny/', data)
        if user:
            force_authenticate(request, user=user)
        response = api.confirm_match.confrim_match(request)
        assert response, isinstance(response, Response)
        return response  # type: ignore

    def test_sucessfull_register(self):
        """ Fully valid register """
        response = register_user(valid_request_data)
        assert response.status_code == 200
        
    # def _create_two_user_prematching(self): TODO
        
    # def test_prematch_creation_mail(self): TODO