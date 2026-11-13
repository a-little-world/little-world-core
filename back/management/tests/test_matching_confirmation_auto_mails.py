from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from management.api.proposed_match_response import respond_to_proposed_match
from management.api.register import Register
from management.tests.helpers import register_user_api

valid_request_data = dict(
    email="benjamin.tim@gmx.de",
    first_name="Tim",
    second_name="Schupp",
    password1="Test123!",
    password2="Test123!",
    birth_year=1984,
    user_type="learner",
)

valid_create_data = dict(
    email=valid_request_data["email"],
    password=valid_request_data["password1"],
    first_name=valid_request_data["first_name"],
    second_name=valid_request_data["second_name"],
    birth_year=valid_request_data["birth_year"],
)


class MatchConfirmationTasksTests(TestCase):
    required_params = Register.required_args

    def _respond_to_proposed_match(self, data: dict, user=None) -> Response:
        factory = APIRequestFactory(enforce_csrf_checks=True)

        request = factory.post("user/match/proposal/respond/", data)
        if user:
            force_authenticate(request, user=user)
        response = respond_to_proposed_match(request)
        assert response, isinstance(response, Response)
        return response  # type: ignore

    def test_sucessfull_register(self):
        """Fully valid register"""
        response = register_user_api(valid_request_data)
        assert response.status_code == 200

    # def _create_two_user_prematching(self): TODO

    # def test_prematch_creation_mail(self): TODO
