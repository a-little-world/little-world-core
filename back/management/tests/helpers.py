from django.test import TestCase
from rest_framework.test import RequestsClient
import json
from rest_framework.response import Response
from management.controller import create_user, get_user_by_email, match_users
from management.api.user_data import get_user_models
from django.conf import settings
from management.models import profile
from management.models import profile
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.sessions.middleware import SessionMiddleware
from management.api import register

def register_user(data: dict) -> Response:
    factory = APIRequestFactory(enforce_csrf_checks=True)
    request = factory.post('/api/register/', data)
    middleware = SessionMiddleware(lambda x: x)
    middleware.process_request(request)
    request.session.save()
    # This will always return the type Optional[Reponse] but pylance doesn't beleave me
    response = register.Register.as_view()(request)
    assert response, isinstance(response, Response)
    return response  # type: ignore
