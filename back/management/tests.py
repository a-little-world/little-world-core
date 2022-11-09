from django.test import TestCase
import json
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from . import api


class RegisterTests(TestCase):

    required_params = api.register.Register.required_args

    valid_request_data = dict(
        email='benjamin.tim@gmx.de',
        first_name='Tim',
        second_name='Schupp',
        password1='Test123!',
        password2='Test123!',
        birth_year=1984
    )

    def _some_register_call(self, data: dict) -> Response:
        factory = APIRequestFactory(enforce_csrf_checks=True)
        request = factory.post('/api/v1/register/', data)
        # This will always return the type Optional[Reponse] but pylance doesn't beleave me
        response = api.register.Register.as_view()(request)
        assert response, isinstance(response, Response)
        return response  # type: ignore

    def test_sucessfull_register(self):
        """ Fully valid register """
        response = self._some_register_call(self.valid_request_data)
        assert response.status_code == 200

    def test_w_missing_params(self):
        """ Request with missing params """
        datas = []
        for parm in self.required_params:
            partial_data = self.valid_request_data.copy()
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
            _data = self.valid_request_data.copy()
            _data["password1"] = passwords[i]
            _data["password2"] = passwords[i]
            datas.append(_data)
        for d in datas:
            response = self._some_register_call(d)
            assert response.status_code == 400

    def test_registered_user_valid(self):
        """
        In `test_sucessfull_register` we register a user
        this should always create 4 db objects: `Settings`, `Profile`, `State`, `User`
        here we check if all where correctly created
        """
        pass  # TODO

    def test_api_fuctions_blocked_email_unverified(self):
        """
        Most api functions should be blocked untill the users email was verified
        They should return 401 unauthorized, 
        with a message saying in order to access this API the email has to be verified
        """
        pass  # TODO

    def test_password_missmatch(self):
        """ Register with password missmatch """
        _data = self.valid_request_data.copy()
        _data["password2"] = str(reversed(_data["password1"]))
        response = self._some_register_call(_data)
        assert response.status_code == 400

    def test_unallowed_chars_in_name(self):
        false_names = ["with space", "with!",
                       "chat_what", "no.name", "any@body"]
        for field in ["first_name", "second_name"]:
            for n in false_names:
                _data = self.valid_request_data.copy()
                _data[field] = n
                response = self._some_register_call(_data)
                assert response.status_code == 400

    def test_register_existing_user(self):
        """ Registring a user that alredy has an account """
        # Not we have to register him sucessfull first, cause tests always reset the DB
        response = self._some_register_call(self.valid_request_data)
        assert response.status_code == 200
        response = self._some_register_call(self.valid_request_data)
        assert response.status_code == 400

    def test_email_verification_enforced(self):
        """ Test that user has to verify email before being able to render the app """
        pass  # TODO


class AdminApiTests(TestCase):
    def test_user_list():
        pass
