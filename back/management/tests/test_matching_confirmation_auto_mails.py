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
from management.models.profile import Profile
from management.models.unconfirmed_matches import UnconfirmedMatch
from management.models.matches import Match

from management.models.unconfirmed_matches import get_unconfirmed_matches
from management.matching.matching_score import calculate_directional_score_write_results_to_db
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

    def _some_register_call(self, data: dict) -> Response:
        factory = APIRequestFactory(enforce_csrf_checks=True)
        request = factory.post('/api/register/', data)
        # This will always return the type Optional[Reponse] but pylance doesn't beleave me
        response = api.register.Register.as_view()(request)
        assert response, isinstance(response, Response)
        return response  # type: ignore
    
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
        response = self._some_register_call(valid_request_data)
        assert response.status_code == 200
        
    # TODO: test depricated
    def _create_two_user_prematching(self):
        users = create_abunch_of_users(2)
        # these test users are fully random, so I'll adjust their profile in a way that they match
        u1, u2 = users

        # make both users be match-able
        modify_profile_to_match(u1, u2)
        
        # to even perform the scoring we need to create a default scoring table source

        # calculate matching score
        # TODO: test depricated we have new way to check matchability
        score = calculate_directional_score_write_results_to_db(
            u1, u2, return_on_nomatch=False, catch_exceptions=True)

        # make the matching proposal
        proposal = create_user_matching_proposal({u1, u2}, send_confirm_match_email=True)

        u1_unconf = get_unconfirmed_matches(u1)
        u2_unconf = get_unconfirmed_matches(u2)
        
        # the modify profile function alsways make the first user the volunteer
        assert u1.profile.user_type == Profile.TypeChoices.VOLUNTEER
        assert u2.profile.user_type == Profile.TypeChoices.LEARNER
        assert len(u1_unconf) == 0, "Volunteer shouldn't be bothered with the pre-matchining selection"
        assert len(u2_unconf) == 1, "Pre matching selection must be present for the learner"
        
        return proposal
        
    def test_prematch_creation_mail(self):

        from emails.models import EmailLog
        
        proposal = self._create_two_user_prematching()
        
        learner = proposal.get_learner()
        volunteer = proposal.get_partner(learner)
        
        print("TBS", "\n,".join([str(vars(el)) for el in EmailLog.objects.all()]))
        
        # At least one 'confirm_match_mail_1' should be present
        matching_proposal_mail = EmailLog.objects.filter(receiver=learner, template='confirm_match_mail_1')
        assert matching_proposal_mail.exists()
        matching_proposal_mail = matching_proposal_mail.first()
        
        # The volunteer should not have any emails!
        assert not EmailLog.objects.filter(receiver=volunteer, template='confirm_match_mail_1').exists()
        
        # Check if the name of the match was correctly inserted in the email
        
        assert matching_proposal_mail.data['params']['match_first_name'] == volunteer.profile.first_name
        assert matching_proposal_mail.data['params']['first_name'] == learner.profile.first_name
        
        print("Pre-matching mail test sucessfull!")
        
        # Now this was easy, but to thest the automatic email reminders we'll need to travel in time a little bit.