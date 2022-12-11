from django.test import TestCase
from rest_framework.test import RequestsClient
import json
from rest_framework.response import Response
from management.api.trans import get_trans_as_tag_catalogue
from management.controller import create_user, get_user_by_email, match_users
from management.api.user_data import get_user_models
from django.conf import settings
from management.models import profile
from rest_framework.test import APIRequestFactory, force_authenticate
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


class ProfileApiTests(TestCase):

    def _get_profile_call(self, auth_usr) -> Response:  # type: ignore
        factory = APIRequestFactory(enforce_csrf_checks=True)

        request = factory.get('/api/profile')
        force_authenticate(request, user=auth_usr)
        # This will always return the type Optional[Reponse] but pylance doesn't beleave me
        response = api.profile.ProfileViewSet.as_view({"get": "_get"})(request)
        assert isinstance(response, Response)
        return response

    def _some_profile_call(self, data: dict, auth_usr) -> Response:  # type: ignore
        factory = APIRequestFactory(enforce_csrf_checks=True)
        request = factory.post('/api/profile/', data)
        # This will always return the type Optional[Reponse] but pylance doesn't beleave me
        force_authenticate(request, user=auth_usr)
        response = api.profile.ProfileViewSet.as_view(
            {"post": "partial_update"})(request)
        assert isinstance(response, Response)
        return response

    def _some_register_call(self, data: dict) -> Response:
        factory = APIRequestFactory(enforce_csrf_checks=True)
        request = factory.post('/api/register/', data)
        # This will always return the type Optional[Reponse] but pylance doesn't beleave me
        response = api.register.Register.as_view()(request)
        assert isinstance(response, Response)
        return response  # type: ignore

    def test_invalid_postal_code(self):
        self._some_register_call(valid_request_data)
        usr = get_user_by_email(valid_request_data["email"])
        for code in [
            "asdgads",  # Letters not allowed postalcode
            "12",
            "ad2134"
        ]:
            resp = self._some_profile_call({"postal_code": code}, usr)
            assert resp.status_code == 400

    def test_valid_postal_code(self):
        self._some_register_call(valid_request_data)
        usr = get_user_by_email(valid_request_data["email"])
        for code in [
            "52062",
            "04230"
        ]:
            resp = self._some_profile_call({"postal_code": code}, usr)
            assert resp.status_code == 200

    def dont_test_change_values_all(self):
        # TODO: currently disabled due to the introduction of string choices
        """
        Tests a lot of possible value for all values that can be changed
        """
        # All fields that the user can change are also all fields that are listed for him:
        allowed_to_change = profile.SelfProfileSerializer.Meta.fields
        self._some_register_call(valid_request_data)
        usr = get_user_by_email(valid_request_data["email"])
        s_profile = profile.SelfProfileSerializer(usr.profile)
        options = profile.ProfileSerializer.get_options(s_profile, usr.profile)
        resp = self._get_profile_call(usr)
        assert resp.status_code == 200
        resp.render()
        cur_usr_data = json.loads(resp.content)
        assert cur_usr_data["user_type"] == "volunteer", "user_type volunteer is the default"

        _last_option_of_key = {}
        # Now for all options we test *all* possible values, and one impossible value
        for option_list_key in options:
            for option in options[option_list_key]:
                # Always overwritten so in the end this contains the last option!:
                _last_option_of_key[option_list_key] = [option]
                _data = {option_list_key: option["value"]}
                if option_list_key == "interests":  # In this case the api does expect a list!
                    _data = {option_list_key: [option["value"]]}
                resp = self._some_profile_call(_data, usr)
                assert resp.status_code == 200
                resp.render()
                resp_content = json.loads(resp.content)
                print(resp_content, option_list_key)
                # Check if the value changed to what we expected
                assert resp_content[option_list_key] == _data[option_list_key]
                # check if the model contains the same data as was returned by the response
                profile_val = getattr(usr.profile, option_list_key)
                # print("Profileval", profile_val)
                # Multiple choices do return sets, that is why we check for list(profileval)
                if option_list_key == "interests":
                    assert list(profile_val) == _data[option_list_key]
                else:
                    assert profile_val == _data[option_list_key]

        for option_list_key in _last_option_of_key:
            for option in _last_option_of_key[option_list_key]:
                # Now this should not be possible anymore! :
                _data = {option_list_key: (option["value"] + 1)}
                resp = self._some_profile_call(_data, usr)
                assert resp.status_code == 400
                resp.render()
                resp_content = json.loads(resp.content)
                # Check if the value changed to what we expected
                assert resp_content[option_list_key] != _data[option_list_key]
                # check if the model contains the same data as was returned by the response
                assert getattr(
                    usr.profile, option_list_key) != _data[option_list_key]

    def test_cant_be_changed_all(self):
        allowed_to_change = profile.SelfProfileSerializer.Meta.fields
        self._some_register_call(valid_request_data)
        usr = get_user_by_email(valid_request_data["email"])
        all_fields = profile.ProfileSerializer(usr.profile).data.keys()
        all_fields_blocked_change = set(
            all_fields).difference(set(allowed_to_change))
        all_fields_blocked_change.remove("options")  # This is a meta field
        # TODO: this field is not used yet
        all_fields_blocked_change.remove("past_user_types")
        print("BLOCKED FOR CHANGE:", all_fields_blocked_change)

        for field in all_fields_blocked_change:
            value = getattr(usr.profile, field)
            # We just try to set it to the current value and it 'should' be blocked!
            _v = value
            if isinstance(value, int):
                _v += 1
            _data = {field: _v}
            resp = self._some_profile_call(_data, usr)
            resp.render()
            if isinstance(value, int):
                # Using an unknow property will not cause an error but it sholdn't change the value
                assert getattr(usr.profile, field) != _v

        # TODO: this test could be somewhat more complete!
