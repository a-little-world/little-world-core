from django.test import TestCase
import json
from rest_framework.response import Response
from management.controller import create_user
from rest_framework.test import APIRequestFactory
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
        request = factory.post('/api/v1/register/', data)
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
        _data = valid_request_data.copy()
        _data["password2"] = str(reversed(_data["password1"]))
        response = self._some_register_call(_data)
        assert response.status_code == 400

    def test_unallowed_chars_in_name(self):
        false_names = ["with space", "with!",
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
        pass

    def test_management_user_created(self):
        pass

    def test_user_list(self):
        pass
