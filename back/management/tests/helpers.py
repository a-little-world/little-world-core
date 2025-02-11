from django.contrib.sessions.middleware import SessionMiddleware
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from management.api import register
from management.controller import get_user_by_email

valid_register_request_data = dict(
    email="benjamin.tim@gmx.de",
    first_name="Tim",
    second_name="Schupp",
    password1="Test123!",
    password2="Test123!",
    birth_year=1984,
)

valid_profile_data = dict(
    email=valid_register_request_data["email"],
    password=valid_register_request_data["password1"],
    first_name=valid_register_request_data["first_name"],
    second_name=valid_register_request_data["second_name"],
    birth_year=valid_register_request_data["birth_year"],
)

GLOB_TEST_USER_COUNT = 0
CREATED_USERS = []


def assure_default_data(data=None):
    global GLOB_TEST_USER_COUNT, CREATED_USERS
    if data is None:
        data = valid_register_request_data
        data["email"] = data["email"].split("@")[0] + str(GLOB_TEST_USER_COUNT) + "@" + data["email"].split("@")[1]
        GLOB_TEST_USER_COUNT += 1
        CREATED_USERS.append(data)
    return data


def register_user_api(data=None) -> Response:
    data = assure_default_data(data)
    factory = APIRequestFactory(enforce_csrf_checks=True)
    request = factory.post("/api/register/", data)
    middleware = SessionMiddleware(lambda x: x)
    middleware.process_request(request)
    request.session.save()
    # This will always return the type Optional[Reponse] but pylance doesn't beleave me
    response = register.Register.as_view()(request)
    assert response, isinstance(response, Response)
    return response


def register_user(data=None) -> Response:
    data = assure_default_data(data)
    response = register_user_api(data=data)
    assert response.status_code == 200
    user = get_user_by_email(data["email"])
    return user
