from django.test import TestCase
from rest_framework.test import RequestsClient
from rest_framework.response import Response
from management.controller import create_user, get_user_by_email, match_users
from management.api.user_data import get_user_models
from django.conf import settings
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.sessions.middleware import SessionMiddleware
from management.api import register

valid_register_request_data = dict(
    email='benjamin.tim@gmx.de',
    first_name='Tim',
    second_name='Schupp',
    password1='Test123!',
    password2='Test123!',
    birth_year=1984
)

valid_profile_data = dict(
    email=valid_register_request_data['email'],
    password=valid_register_request_data['password1'],
    first_name=valid_register_request_data['first_name'],
    second_name=valid_register_request_data['second_name'],
    birth_year=valid_register_request_data['birth_year'],
)

def register_user(data: dict = valid_register_request_data) -> Response:
    factory = APIRequestFactory(enforce_csrf_checks=True)
    request = factory.post('/api/register/', data)
    middleware = SessionMiddleware(lambda x: x)
    middleware.process_request(request)
    request.session.save()
    # This will always return the type Optional[Reponse] but pylance doesn't beleave me
    response = register.Register.as_view()(request)
    assert response, isinstance(response, Response)
    return response  # type: ignore
