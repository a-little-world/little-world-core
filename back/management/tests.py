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
from . import api

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


class RegisterTests(TestCase):

    required_params = api.register.Register.required_args

    def _some_register_call(self, data: dict) -> Response:
        factory = APIRequestFactory(enforce_csrf_checks=True)
        request = factory.post('/api/register/', data)
        # This will always return the type Optional[Reponse] but pylance doesn't beleave me
        response = api.register.Register.as_view()(request)
        assert response, isinstance(response, Response)
        return response  # type: ignore

    def test_sucessfull_register(self):
        """ Fully valid register """
        response = self._some_register_call(valid_request_data)
        assert response.status_code == 200

    def test_w_missing_params(self):
        """ Request with missing params """
        datas = []
        for parm in self.required_params:
            partial_data = valid_request_data.copy()
            del partial_data[parm]
            datas.append(partial_data)
        for i, d in enumerate(datas):
            response = self._some_register_call(d)
            assert response.status_code == 400
            response.render()
            # Assert that the fields in in response ( otherwiese the 400 could have happend for a different reason )
            assert self.required_params[i] in json.loads(response.content)

    def test_weak_password_validation_fail(self):
        """ Test a couple to weak passwords """
        passwords = ["Test123", "abcdefg", "password"]
        datas = []
        for i, v in enumerate(passwords):
            _data = valid_request_data.copy()
            _data["password1"] = passwords[i]
            _data["password2"] = passwords[i]
            datas.append(_data)
        for d in datas:
            response = self._some_register_call(d)
            assert response.status_code == 400

    def test_register_first_name_normalized(self):
        _data = valid_request_data.copy()
        random_capilalization = "FirstNameAm"
        _data["first_name"] = random_capilalization
        response = self._some_register_call(_data)
        assert response.status_code == 200
        usr = get_user_by_email(_data["email"])
        assert usr.first_name == random_capilalization[:1].upper(
        ) + random_capilalization[1:].lower(), usr.first_name

    def test_register_first_name_beginning_end_space_ignored(self):
        _data = valid_request_data.copy()
        random_typed = " FirstNameAm   "
        _data["first_name"] = random_typed
        response = self._some_register_call(_data)
        assert response.status_code == 200
        usr = get_user_by_email(_data["email"])
        random_typed = random_typed.strip()
        norm_rand = (random_typed[:1].upper() + random_typed[1:].lower())
        assert usr.first_name == norm_rand, usr.first_name

    def test_register_second_name_space_in_name(self):
        _data = valid_request_data.copy()
        random_typed = "second name"
        _data["second_name"] = random_typed
        response = self._some_register_call(_data)
        assert response.status_code == 200
        usr = get_user_by_email(_data["email"])
        assert usr.last_name == random_typed.title()

    def test_register_second_name_multiple_space_in_name(self):
        _data = valid_request_data.copy()
        random_typed = "second n ame"
        _data["second_name"] = random_typed
        response = self._some_register_call(_data)
        assert response.status_code == 400  # Muliple space are now allowed!

    def test_register_email_normalized(self):
        _data = valid_request_data.copy()
        random_capilalization = "TesT@uSr.com"
        _data["email"] = random_capilalization
        response = self._some_register_call(_data)
        assert response.status_code == 200
        usr = get_user_by_email(_data["email"].lower())
        assert usr.email == random_capilalization.lower()

    def test_registered_user_valid(self):
        """
        In `test_sucessfull_register` we register a user
        this should always create 4 db objects: `Settings`, `Profile`, `State`, `User`
        here we check if all where correctly created
        """
        response = self._some_register_call(valid_request_data)
        assert response.status_code == 200
        # If this failes user creation is broken:
        user = get_user_by_email(valid_request_data['email'])
        # If this failes the other user models where somehow not created:
        _ = get_user_models(user)

    def test_api_fuctions_blocked_email_unverified(self):
        """
        Most api functions should be blocked untill the users email was verified
        They should return 401 unauthorized, 
        with a message saying in order to access this API the email has to be verified
        """
        pass  # TODO

    def test_password_missmatch(self):
        """ Register with password missmatch """
        _data = valid_request_data.copy()
        _data["password2"] = str(reversed(_data["password1"]))
        response = self._some_register_call(_data)
        assert response.status_code == 400

    def test_unallowed_chars_in_name(self):
        false_names = ["with multi space", "with!",
                       "chat_what", "no.name", "any@body"]
        for field in ["first_name", "second_name"]:
            for n in false_names:
                _data = valid_request_data.copy()
                _data[field] = n
                response = self._some_register_call(_data)
                assert response.status_code == 400

    def test_register_existing_user(self):
        """ Registring a user that alredy has an account """
        # Not we have to register him sucessfull first, cause tests always reset the DB
        response = self._some_register_call(valid_request_data)
        assert response.status_code == 200
        response = self._some_register_call(valid_request_data)
        assert response.status_code == 400

    def test_email_verification_enforced(self):
        """ Test that user has to verify email before being able to render the app """
        pass  # TODO

    def test_base_admin_created_if_no_users(self):
        response = self._some_register_call(valid_request_data)
        assert response.status_code == 200
        # v-- base managment user should be automaticly created:
        usr = get_user_by_email(settings.MANAGEMENT_USER_MAIL)

        # would error if the user doesn't exist...

    def test_auto_login_after_register(self):
        response = self._some_register_call(valid_request_data)
        assert response.status_code == 200
        usr = get_user_by_email(valid_create_data["email"])
        # now if we render /app we should be redirected to /login
        client = RequestsClient()
        response = client.get('http://localhost:8000/app')
        print(response)

    def test_mail_verification(self):
        """
        Tests if mail code was generate and we can verify it
        """
        response = self._some_register_call(valid_request_data)
        assert response.status_code == 200
        usr = get_user_by_email(valid_create_data["email"])
        code_b64 = usr.state.get_email_auth_code_b64()
        assert usr.state.check_email_auth_code_b64(code_b64)
        assert usr.state.is_email_verified()
        # Now ok lets set it to unverified again and then check if calling the api also does the trick


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

    def test_change_values_all(self):
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
        assert cur_usr_data["user_type"] == 0, "user_type volunteer is the default"

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


class AdminApiTests(TestCase):
    def _create_abunch_of_users(self, amnt=20):
        mail_count = 0
        mail_fragments = valid_create_data["email"].split("@")

        def _make_mail(count):
            count += 1
            return count, mail_fragments[0] + str(count) + "@" + mail_fragments[1]

        users = []
        for i in range(amnt):
            # 20 test users
            _data = valid_create_data.copy()
            mail_count, _mail = _make_mail(mail_count)
            print(f"Creating user: '_mail'")
            _data['email'] = _mail
            users.append(create_user(**_data))
        return users

    def _match_all(self, users):
        # Matches *all* user in the users list
        stack = users.copy()
        while len(stack) > 1:
            usr = stack.pop(len(stack))  # begin at the highest index
            for _usr in stack:
                match_users({usr, _usr})

    def test_management_user_created(self):
        # Would throw error if users cant be created or
        # If the admin user doesn't yet exist
        users = self._create_abunch_of_users(amnt=4)
        for u in users:
            assert u.state.matches

    def test_matches_made(self):
        users = self._create_abunch_of_users(amnt=20)
        for usr in users:
            get_user_models(usr)["state"].matches

    def test_user_list(self):
        pass


class TestTranslations(TestCase):

    def _get_translations(self):
        context = {}
        for lang in settings.LANGUAGES:
            lang_code = lang[0]

            factory = APIRequestFactory(enforce_csrf_checks=True)
            request = factory.get(f'/api/trans/{lang}')
            context[lang_code] = get_trans_as_tag_catalogue(request, lang_code)
            assert context[lang_code], "Translation dict emtpy!"
        return context

    def test_all_tags_translated(self):
        """ 
        This test will error if a developer has defined a new translation string using pgettext(tag, string)
        But has not trasnlated it to all laguages
        ---> In the future this test might be ignored, 
        but for now this is a good check so that there will never be a trasnlation tag in the frontend which is not translated!
        """
        context = self._get_translations()

        non_tag_lang = [l[0] for l in settings.LANGUAGES if l[0] != "tag"]
        missing_trans = {l: [] for l in non_tag_lang}
        for k in context["tag"]:
            for lang in non_tag_lang:
                if k not in context[lang]:
                    missing_trans[lang].append(k)
        assert all([missing_trans[l] for l in non_tag_lang]
                   ), f"There are missing translations:\n" \
            + '\n'.join([f"Lang: '{l}':\n" + '\n'.join([t for t in missing_trans[l]])
                        for l in non_tag_lang])
