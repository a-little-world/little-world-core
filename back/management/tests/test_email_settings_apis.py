from django.test import TestCase
from rest_framework.response import Response
from management.controller import get_user_by_email
from management.tests.helpers import register_user
from rest_framework.test import APIRequestFactory, force_authenticate
from .. import api

valid_request_data = dict(
    email="benjamin.tim@gmx.de",
    first_name="Tim",
    second_name="Schupp",
    password1="Test123!",
    password2="Test123!",
    birth_year=1984,
)

valid_create_data = dict(
    email=valid_request_data["email"],
    password=valid_request_data["password1"],
    first_name=valid_request_data["first_name"],
    second_name=valid_request_data["second_name"],
    birth_year=valid_request_data["birth_year"],
)


class EmailSettingsTests(TestCase):
    required_params = api.register.Register.required_args

    def test_email_correctly_normalized(self):
        response = register_user(valid_request_data)
        user = get_user_by_email(valid_request_data["email"])
        orig_email = user.email
        new_email = orig_email.replace("@", "+Test@")

        factory = APIRequestFactory(enforce_csrf_checks=True)
        request = factory.post("/api/user/change_email/", {"email": new_email})
        force_authenticate(request, user=user)
        response = api.user.ChangeEmailApi.as_view()(request)

        assert response.status_code == 200
        assert user.email == new_email.lower()

    # def test_email_unsubscribe_link_get(self): TODO: create new test for new apis

    def test_password_reset_by_email(self):
        # create the test user
        response = register_user(valid_request_data)

        # check if we can request a password change for this user
        response = self.client.post(
            "/api/user/resetpw/",
            data={"email": valid_request_data["email"]},
            format="json",
        )
        assert response.status_code == 200

        # check for a from email format
        response = self.client.post(
            "/api/user/resetpw/",
            data={"email": "tim@timschupp+420@gmail.com"},
            format="json",
        )
        assert response.status_code == 400

        # check for aunknown email
        response = self.client.post(
            "/api/user/resetpw/",
            data={"email": "not_in_db@unknown.test"},
            format="json",
        )
        assert response.status_code == 200
