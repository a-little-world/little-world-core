from django.test import TestCase
from rest_framework.test import RequestsClient
import json
from management.controller import get_user_by_email
from management.tests.helpers import register_user, valid_register_request_data, register_user_api
from django.conf import settings
from .. import api


class RegisterTests(TestCase):
    required_params = api.register.Register.required_args

    def test_sucessfull_register(self):
        """Fully valid register"""
        user = register_user(valid_register_request_data)

    def test_w_missing_params(self):
        """Request with missing params"""
        datas = []
        for parm in self.required_params:
            partial_data = valid_register_request_data.copy()
            del partial_data[parm]
            datas.append(partial_data)
        for i, d in enumerate(datas):
            response = register_user_api(d)
            assert response.status_code == 400
            response.render()
            # Assert that the fields in in response ( otherwiese the 400 could have happend for a different reason )
            assert self.required_params[i] in json.loads(response.content)

    def test_weak_password_validation_fail(self):
        """Test a couple to weak passwords"""
        passwords = ["Test123", "abcdefg", "password"]
        datas = []
        for i, v in enumerate(passwords):
            _data = valid_register_request_data.copy()
            _data["password1"] = passwords[i]
            _data["password2"] = passwords[i]
            datas.append(_data)
        for d in datas:
            response = register_user_api(d)
            assert response.status_code == 400

    def test_register_first_name_normalized(self):
        _data = valid_register_request_data.copy()
        random_capilalization = "FirstNameAm"
        _data["first_name"] = random_capilalization
        response = register_user_api(_data)
        assert response.status_code == 200
        usr = get_user_by_email(_data["email"])
        assert usr.first_name == random_capilalization[:1].upper() + random_capilalization[1:].lower(), usr.first_name

    def test_register_first_name_beginning_end_space_ignored(self):
        _data = valid_register_request_data.copy()
        random_typed = " FirstNameAm   "
        _data["first_name"] = random_typed
        response = register_user_api(_data)
        assert response.status_code == 200
        usr = get_user_by_email(_data["email"])
        random_typed = random_typed.strip()
        norm_rand = random_typed[:1].upper() + random_typed[1:].lower()
        assert usr.first_name == norm_rand, usr.first_name

    def test_register_second_name_space_in_name(self):
        _data = valid_register_request_data.copy()
        random_typed = "second name"
        _data["second_name"] = random_typed
        response = register_user_api(_data)
        assert response.status_code == 200
        usr = get_user_by_email(_data["email"])
        assert usr.last_name == random_typed.title()

    def test_register_second_name_multiple_space_in_name(self):
        _data = valid_register_request_data.copy()
        random_typed = "second n ame"
        _data["second_name"] = random_typed
        user = register_user(_data)

    def test_register_second_name_multispace(self):
        response = register_user_api(valid_register_request_data)
        assert response.status_code == 200

        _data = valid_register_request_data.copy()

        _data["email"] = "randomemail1@mail.test"
        _data["second_name"] = "a long surname with many spaces"
        user = register_user(_data)

        _data["email"] = "randomemail2@mail.test"
        _data["second_name"] = "surname  with to many spaces"
        failed = False
        try:
            user = register_user(_data)
        except Exception:
            failed = True
        assert failed

    def test_register_email_normalized(self):
        _data = valid_register_request_data.copy()
        random_capilalization = "TesT@uSr.com"
        _data["email"] = random_capilalization
        response = register_user_api(_data)
        assert response.status_code == 200
        usr = get_user_by_email(_data["email"].lower())
        assert usr.email == random_capilalization.lower()

    def test_api_fuctions_blocked_email_unverified(self):
        """
        Most api functions should be blocked untill the users email was verified
        They should return 401 unauthorized,
        with a message saying in order to access this API the email has to be verified
        """
        pass  # TODO

    def test_password_missmatch(self):
        """Register with password missmatch"""
        _data = valid_register_request_data.copy()
        _data["password2"] = str(reversed(_data["password1"]))
        response = register_user_api(_data)
        assert response.status_code == 400

    def test_unallowed_chars_in_name(self):
        false_names = ["with!", "chat_what", "no.name", "any@body"]
        for field in ["first_name", "second_name"]:
            for n in false_names:
                _data = valid_register_request_data.copy()
                _data[field] = n
                response = register_user_api(_data)
                assert response.status_code == 400

    def test_register_existing_user(self):
        """Registring a user that alredy has an account"""
        # Not we have to register him sucessfull first, cause tests always reset the DB
        response = register_user_api(data=valid_register_request_data)
        assert response.status_code == 200
        response = register_user_api(data=valid_register_request_data)
        assert response.status_code == 400

    def test_email_verification_enforced(self):
        """Test that user has to verify email before being able to render the app"""
        pass  # TODO

    def test_base_admin_created_if_no_users(self):
        response = register_user_api(valid_register_request_data)
        assert response.status_code == 200
        # v-- base managment user should be automaticly created:
        usr = get_user_by_email(settings.MANAGEMENT_USER_MAIL)

    def test_auto_login_after_register(self):
        usr = register_user(valid_register_request_data)
        # now if we render /app we should be redirected to /login
        client = RequestsClient()
        response = client.get("http://localhost:8000/app")
        # TODO: check if the main frontend renders correctly
        print(response)

    def test_mail_verification(self):
        """
        Tests if mail code was generate and we can verify it
        """
        usr = register_user(valid_register_request_data)
        code_b64 = usr.state.get_email_auth_code_b64()
        assert usr.state.check_email_auth_code_b64(code_b64)
        assert usr.state.is_email_verified()

    def test_space_in_email_allowed_and_removed(self):
        pass  # TODO: Test is spaces at the biginning and end of an emails are allowed and working
