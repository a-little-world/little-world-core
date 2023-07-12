from django.test import TestCase
from rest_framework.test import RequestsClient
import json
from rest_framework.response import Response
from management.api.trans import get_trans_as_tag_catalogue
from management.controller import create_user, get_user_by_email, match_users, create_user_matching_proposal
from management.api.user_data import get_user_models
from django.conf import settings
from rest_framework.test import APIRequestFactory, force_authenticate
from management.random_test_users import create_abunch_of_users, modify_profile_to_match
from management.models import EmailSettings
from management.models.unconfirmed_matches import get_unconfirmed_matches
from management.matching.matching_score import calculate_directional_score_write_results_to_db
from management.tasks import create_default_table_score_source
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


class EmailSettingsTests(TestCase):

    required_params = api.register.Register.required_args

    def _some_register_call(self, data: dict) -> Response:
        factory = APIRequestFactory(enforce_csrf_checks=True)
        request = factory.post('/api/register/', data)
        # This will always return the type Optional[Reponse] but pylance doesn't beleave me
        response = api.register.Register.as_view()(request)
        assert response, isinstance(response, Response)
        return response  # type: ignore
    
    def test_email_unsubscribe_link_get(self):
        response = self._some_register_call(valid_request_data)
        
        user = get_user_by_email(valid_request_data['email'])
        settings_hash = str(user.settings.email_settings.hash)

        link = f"/api/emails/toggle_sub?settings_hash={settings_hash}&choice=False&sub_type=interview_requests"

        factory = APIRequestFactory(enforce_csrf_checks=True)
        request = factory.get(link)
        force_authenticate(request, user=user)
        
        response = api.email_settings.unsubscribe_link(request)
        
        assert response.status_code == 200
        
        print("RESPONSE",response.content)
        
        user = get_user_by_email(valid_request_data['email'])
        print("TBS", str(user.settings.email_settings.unsubscibed_options))
        
        
        # Check if actually unsubscribed now
        assert 'interview_requests' in user.settings.email_settings.unsubscibed_options, str(user.settings.email_settings.unsubscibed_options)