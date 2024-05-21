from django.test import TestCase
from rest_framework.test import RequestsClient
import json
from rest_framework.response import Response
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

    def test_space_in_email_allowed_and_removed(self):
        pass  # TODO: Test is spaces at the biginning and end of an emails are allowed and working
