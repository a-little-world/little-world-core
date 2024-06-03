from django.test import TestCase
from rest_framework.test import RequestsClient
import json
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from management.random_test_users import create_abunch_of_users, modify_profile_to_match
from management.models.profile import Profile
from management.models.unconfirmed_matches import ProposedMatch
from management.models.matches import Match
from management.models.unconfirmed_matches import get_unconfirmed_matches
from management import api

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


class MatchConfirmationTests(TestCase):

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
        
    # TODO: user match creation depricated possibly sinc ethe score cacluation has been depricate 
    def _create_two_user_prematching(self):
        users = create_abunch_of_users(2)
        # these test users are fully random, so I'll adjust their profile in a way that they match
        u1, u2 = users

        # make both users be match-able
        modify_profile_to_match(u1, u2)
        

        # TODO have new wayt to test matchability

        # calculate matching score
        score = calculate_directional_score_write_results_to_db(
            u1, u2, return_on_nomatch=False, catch_exceptions=True)

        # make the matching proposal
        create_user_matching_proposal({u1, u2}, send_confirm_match_email=False)

        # check if the matching proposal was created
        
        u1_unconf = get_unconfirmed_matches(u1)
        u2_unconf = get_unconfirmed_matches(u2)
        
        # the modify profile function alsways make the first user the volunteer
        assert u1.profile.user_type == Profile.TypeChoices.VOLUNTEER
        assert u2.profile.user_type == Profile.TypeChoices.LEARNER
        assert len(u1_unconf) == 0, "Volunteer shouldn't be bothered with the pre-matchining selection"
        assert len(u2_unconf) == 1, "Pre matching selection must be present for the learner"
        
        print("u1_unconf", u1_unconf)
        print("u2_unconf", u2_unconf)
        return u1, u2
    
    # TODO: create test for the pre-match email being send out
    # TODO: check if the link in the pre-match email is valid and leads to the correct page

    def test_making_deny_pre_matching(self):
        """
        Basicy for two users generate the matching scores, then try to match them 
        but deny the pre-matching, so there should be no match made!
        """
        u1, u2 = self._create_two_user_prematching()

        u1_unconf = get_unconfirmed_matches(u1)
        u2_unconf = get_unconfirmed_matches(u2)
        
        unconf_hash = u2_unconf[0]["hash"]
        prematch_hash = u2_unconf[0]["user_hash"]
        
        assert u1.hash == prematch_hash, "The prematch hash must be the hash of the volunteer"
        
        # now we emulate the two cases of the learner accepting or denying the pre-match
        res = self._some_confirm_deny_match_call(dict(
           unconfirmed_match_hash = unconf_hash,
           confirm = False
        ), user=u2)
        
        res.render()
        assert res.status_code == 200, f"Request error {res.status_code}, {res.content}"
        print("RES", str(res.content))
        
        # now check if the user is in the matches
        # TODO: test need to be updated using the new 'Match' model
        assert not (u1 in u2.state.matches.all()), "The learner must NOT be in the matches of the volunteer"
        assert not (u2 in u1.state.matches.all()), "The volunteer must NOT be in the matches of the learner"
        
        # This is new stategy
        matching = Match.get_match(u1, u2)
        assert not matching.exists(), "The match must not exist"
        
        # the unconfirmed match must be closed now
        unconf_match_obj = ProposedMatch.objects.get(hash=unconf_hash)
        assert unconf_match_obj.closed, "The unconfirmed match must be closed now"

    def test_making_accept_pre_matching(self):
        """
        Basicy for two users generate the matching scores, then try to match them 
        """
        u1, u2 = self._create_two_user_prematching()

        u1_unconf = get_unconfirmed_matches(u1)
        u2_unconf = get_unconfirmed_matches(u2)
        
        unconf_hash = u2_unconf[0]["hash"]
        prematch_hash = u2_unconf[0]["user_hash"]
        
        assert u1.hash == prematch_hash, "The prematch hash must be the hash of the volunteer"
        
        # now we emulate the two cases of the learner accepting or denying the pre-match
        res = self._some_confirm_deny_match_call(dict(
           unconfirmed_match_hash = unconf_hash,
           confirm = True
        ), user=u2)
        
        res.render()
        assert res.status_code == 200, f"Request error {res.status_code}, {res.content}"
        print("RES", str(res.content))
        
        # now check if the user is in the matches
        # TODO: test need to be updated using the new 'Match' model
        assert u1 in u2.state.matches.all(), "The learner must be in the matches of the volunteer"
        assert u2 in u1.state.matches.all(), "The volunteer must be in the matches of the learner"
        
        # This is new stategy:
        assert Match.get_match(u1, u2).exists(), "The match must exist"
        
        # the unconfirmed match must be closed now
        unconf_match_obj = ProposedMatch.objects.get(hash=unconf_hash)
        assert unconf_match_obj.closed, "The unconfirmed match must be closed now"
