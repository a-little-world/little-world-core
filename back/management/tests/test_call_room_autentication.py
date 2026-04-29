import os

from django.db.models import Q
from django.test import TestCase
from video.models import LiveKitRoom

from management import api
from management.controller import get_user_by_email, match_users
from management.tests.helpers import register_user_api

valid_request_data = dict(
    email="benjamin.tim@gmx.de",
    first_name="Tim",
    second_name="Schupp",
    password1="Test123!",
    password2="Test123!",
    birth_year=1984,
    user_type="learner",
)

valid_create_data = dict(
    email=valid_request_data["email"],
    password=valid_request_data["password1"],
    first_name=valid_request_data["first_name"],
    second_name=valid_request_data["second_name"],
    birth_year=valid_request_data["birth_year"],
)


def _is_on_ci():
    return "CI" in os.environ and os.environ["CI"].lower() in ("true", "1", "t")


class CallRoomTests(TestCase):
    required_params = api.register.Register.required_args

    def create_two_users_match(self):
        datas = [valid_request_data.copy(), valid_request_data.copy()]
        datas[1]["email"] = "benjamin1.tim@gmx.de"

        usrs = []
        for d in datas:
            response = register_user_api(d)
            assert response.status_code == 200
            usr = get_user_by_email(d["email"])
            usrs.append(usr)
        match_users({usrs[0], usrs[1]})
        return usrs[0], usrs[1]

    def test_video_room_creation(self):
        usrs = self.create_two_users_match()
        rooms = LiveKitRoom.objects.filter(
            Q(u1=usrs[0], u2=usrs[1], random_call_room=False) | Q(u1=usrs[1], u2=usrs[0], random_call_room=False)
        )
        assert rooms.count() == 1

    # def test_authenticate_call(self): TODO
