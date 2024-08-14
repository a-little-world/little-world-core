from django.test import TestCase
import json
from rest_framework.response import Response
from management.controller import get_user_by_email
from management.tests.helpers import register_user
from django.conf import settings
from management.models import profile
from rest_framework.test import APIRequestFactory, force_authenticate
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
        factory = APIRequestFactory(
            enforce_csrf_checks=True, content_type='application/json')
        request = factory.post('/api/profile/', data)
        force_authenticate(request, user=auth_usr)
        response = api.profile.ProfileViewSet.as_view(
            {"post": "partial_update"})(request)
        assert isinstance(response, Response)
        return response

    def test_invalid_postal_code(self):
        register_user(valid_request_data)
        usr = get_user_by_email(valid_request_data["email"])
        for code in [
            "asdgads",  # Letters not allowed postalcode
            "12",
            "ad2134"
        ]:
            resp = self._some_profile_call({"postal_code": code}, usr)
            assert resp.status_code == 400

    def test_valid_postal_code(self):
        register_user(valid_request_data)
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
        register_user(valid_request_data)
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
        register_user(valid_request_data)
        usr = get_user_by_email(valid_request_data["email"])
        all_fields = profile.ProfileSerializer(usr.profile).data.keys()
        all_fields_blocked_change = set(
            all_fields).difference(set(allowed_to_change))
        all_fields_blocked_change.remove("options")  # This is a meta field
        # TODO: this field is not used yet
        all_fields_blocked_change.remove("past_user_types")
        all_fields_blocked_change.remove("gender_prediction")
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

    def test_lang_skill_field(self):
        register_user(valid_request_data)
        usr = get_user_by_email(valid_request_data["email"])
        s_profile = profile.SelfProfileSerializer(usr.profile)
        options = profile.ProfileSerializer.get_options(s_profile, usr.profile)
        resp = self._get_profile_call(usr)

        resp = self._some_profile_call(
            {"lang_skill": json.dumps([{"lang": "german", "level": "level-0"}])}, usr)
        assert resp.status_code == 200

        _r = self._get_profile_call(usr)
        _r.render()
        cur_usr_data = json.loads(_r.content)

        # duplicate language
        resp = self._some_profile_call(
            {"lang_skill": [{"lang": "german", "level": "level-0"}, {"lang": "german", "level": "level-0"}]}, usr)
        assert resp.status_code == 400

        # no german included
        resp = self._some_profile_call(
            {"lang_skill": [{"lang": "english", "level": "level-0"}]}, usr)
        assert resp.status_code == 400

        # wrong lang name
        resp = self._some_profile_call(
            {"lang_skill": [{"lang": "german", "level": "level-0"}, {"lang": "bla", "level": "level-0"}]}, usr)
        assert resp.status_code == 400

        # unknown level
        resp = self._some_profile_call(
            {"lang_skill": [{"lang": "german", "level": "level-1213"}]}, usr)
        assert resp.status_code == 400
