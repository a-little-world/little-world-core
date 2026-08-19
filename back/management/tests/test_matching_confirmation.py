from datetime import timedelta
from unittest.mock import patch

from chat.models import Message
from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from management import api
from management.controller import create_user_matching_proposal
from management.models.matches import Match
from management.models.profile import Profile
from management.models.state import State
from management.models.unconfirmed_matches import (
    MatchType,
    ProposedMatch,
    format_suggested_availability_overlap,
    get_unconfirmed_matches,
)
from management.models.user import User
from management.random_test_users import create_abunch_of_users, modify_profile_to_match
from management.tests.helpers import register_user_api
from management.validators import DAYS

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


class MatchConfirmationTests(TestCase):
    required_params = api.register.Register.required_args

    def _respond_to_proposed_match(self, data: dict, user=None) -> Response:
        factory = APIRequestFactory(enforce_csrf_checks=True)

        request = factory.post("user/match/proposal/respond/", data)
        if user:
            force_authenticate(request, user=user)
        response = api.proposed_match_response.respond_to_proposed_match(request)
        assert response, isinstance(response, Response)
        return response  # type: ignore

    def test_formats_suggested_availability_overlap_in_german(self):
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        day = DAYS[tomorrow.weekday()]
        availability1 = {available_day: [] for available_day in DAYS}
        availability2 = {available_day: [] for available_day in DAYS}
        availability1[day] = ["10_12", "12_14", "14_16"]
        availability2[day] = ["10_12", "12_14", "18_20"]

        suggestion = format_suggested_availability_overlap(availability1, availability2)

        assert suggestion.startswith("• ")
        assert f"({tomorrow:%d.%m.})" in suggestion
        assert f"({today:%d.%m.})" not in suggestion
        assert "10-14 Uhr" in suggestion

    def test_formats_top_two_overlaps_on_different_days(self):
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)
        day_one = DAYS[tomorrow.weekday()]
        day_two = DAYS[day_after.weekday()]
        availability1 = {available_day: [] for available_day in DAYS}
        availability2 = {available_day: [] for available_day in DAYS}
        availability1[day_one] = ["10_12", "12_14"]
        availability2[day_one] = ["10_12", "12_14"]
        availability1[day_two] = ["16_18", "18_20"]
        availability2[day_two] = ["16_18", "18_20"]

        suggestion = format_suggested_availability_overlap(availability1, availability2)

        assert suggestion.count("• ") == 2
        assert suggestion.index(f"({tomorrow:%d.%m.})") < suggestion.index(f"({day_after:%d.%m.})")
        assert "16-20 Uhr" in suggestion
        assert "10-14 Uhr" in suggestion

    def test_prefers_best_block_per_day(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        day = DAYS[tomorrow.weekday()]
        availability1 = {available_day: [] for available_day in DAYS}
        availability2 = {available_day: [] for available_day in DAYS}
        availability1[day] = ["08_10", "10_12", "12_14", "16_18", "18_20"]
        availability2[day] = ["08_10", "10_12", "12_14", "16_18", "18_20"]

        suggestion = format_suggested_availability_overlap(availability1, availability2)

        assert suggestion.count("• ") == 1
        assert "08-14 Uhr" in suggestion

    def test_orders_selected_suggestions_by_date(self):
        today = timezone.localdate()
        sooner = today + timedelta(days=1)
        later = today + timedelta(days=4)
        sooner_day = DAYS[sooner.weekday()]
        later_day = DAYS[later.weekday()]
        availability1 = {available_day: [] for available_day in DAYS}
        availability2 = {available_day: [] for available_day in DAYS}
        availability1[sooner_day] = ["10_12"]
        availability2[sooner_day] = ["10_12"]
        availability1[later_day] = ["08_10", "10_12", "12_14"]
        availability2[later_day] = ["08_10", "10_12", "12_14"]

        suggestion = format_suggested_availability_overlap(availability1, availability2)

        assert suggestion.index(f"({sooner:%d.%m.})") < suggestion.index(f"({later:%d.%m.})")

    def test_includes_weekday_in_next_seven_days(self):
        today = timezone.localdate()
        monday_offset = None
        for offset in range(1, 8):
            overlap_date = today + timedelta(days=offset)
            if overlap_date.weekday() == 0:
                monday_offset = offset
                break

        if monday_offset is None:
            return

        today_day = DAYS[today.weekday()]
        availability1 = {available_day: [] for available_day in DAYS}
        availability2 = {available_day: [] for available_day in DAYS}
        availability1[today_day] = ["10_12"]
        availability2[today_day] = ["10_12"]
        availability1["mo"] = ["16_18", "18_20"]
        availability2["mo"] = ["16_18", "18_20"]

        suggestion = format_suggested_availability_overlap(availability1, availability2)
        monday_date = today + timedelta(days=monday_offset)

        assert f"Montag ({monday_date:%d.%m.})" in suggestion
        assert "16-20 Uhr" in suggestion

    def test_sucessfull_register(self):
        """Fully valid register"""
        response = register_user_api(valid_request_data)
        assert response.status_code == 200

    # TODO: user match creation depricated possibly sinc ethe score cacluation has been depricate
    def _create_two_user_prematching(self):
        users = create_abunch_of_users(2)
        # these test users are fully random, so I'll adjust their profile in a way that they match
        u1, u2 = users

        # make both users be match-able
        modify_profile_to_match(u1, u2)
        # TODO have new wayt to test matchability

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

        return u1, u2

    # TODO: create test for the pre-match email being send out
    # TODO: check if the link in the pre-match email is valid and leads to the correct page

    def test_making_deny_pre_matching(self):
        """
        Basicy for two users generate the matching scores, then try to match them
        but deny the pre-matching, so there should be no match made!
        """
        u1, u2 = self._create_two_user_prematching()

        get_unconfirmed_matches(u1)
        u2_unconf = get_unconfirmed_matches(u2)

        unconf_hash = u2_unconf[0]["hash"]
        prematch_uuid = u2_unconf[0]["user_uuid"]

        assert str(u1.uuid) == prematch_uuid, "The prematch UUID must be the UUID of the volunteer"

        # now we emulate the two cases of the learner accepting or denying the pre-match
        res = self._respond_to_proposed_match(dict(unconfirmed_match_uuid=unconf_hash, confirm=False), user=u2)

        res.render()
        assert res.status_code == 200, f"Request error {res.status_code}, {res.content}"
        # now check if the user is in the matches
        # TODO: test need to be updated using the new 'Match' model
        # TODO: test ending was removed since we changes how we actually handle 'matches'

    def test_making_accept_pre_matching(self):
        """
        Basicy for two users generate the matching scores, then try to match them
        """
        u1, u2 = self._create_two_user_prematching()

        get_unconfirmed_matches(u1)
        u2_unconf = get_unconfirmed_matches(u2)

        unconf_hash = u2_unconf[0]["hash"]
        prematch_uuid = u2_unconf[0]["user_uuid"]

        assert str(u1.uuid) == prematch_uuid, "The prematch UUID must be the UUID of the volunteer"
        # now we emulate the two cases of the learner accepting or denying the pre-match
        confirm_message = "Hi, I would be happy to connect with you."
        res = self._respond_to_proposed_match(
            dict(unconfirmed_match_uuid=unconf_hash, confirm=True, confirm_message=confirm_message), user=u2
        )

        res.render()
        assert res.status_code == 200, f"Request error {res.status_code}, {res.content}"
        match = Match.get_match(u1, u2).first()
        assert match is not None
        assert match.total_messages_counter == 1
        assert match.first_interaction_at is not None
        assert Message.objects.filter(sender=u2, recipient=u1, text=confirm_message).exists()
        # Learner (u2) who accepted the proposal is recorded in confirmed_by immediately.
        assert u2 in match.confirmed_by.all()
        assert u1 not in match.confirmed_by.all()
        assert match.confirmed is False

        # Volunteer viewing/confirming completes confirmation.
        match.confirm(u1)
        match.refresh_from_db()
        assert u1 in match.confirmed_by.all()
        assert match.confirmed is True
        # now check if the user is in the matches
        # TODO: test need to be updated using the new 'Match' model
        # TODO: Test ending was removed since we change how we handlel matching & matching confirmations

    def test_making_accept_pre_matching_without_message(self):
        u1, u2 = self._create_two_user_prematching()

        get_unconfirmed_matches(u1)
        u2_unconf = get_unconfirmed_matches(u2)

        unconf_hash = u2_unconf[0]["hash"]

        res = self._respond_to_proposed_match(dict(unconfirmed_match_uuid=unconf_hash, confirm=True), user=u2)

        res.render()
        assert res.status_code == 200, f"Request error {res.status_code}, {res.content}"
        match = Match.get_match(u1, u2).first()
        assert match is not None
        assert match.total_messages_counter == 0
        assert match.first_interaction_at is None
        assert not Message.objects.filter(sender=u2, recipient=u1).exists()
        assert u2 in match.confirmed_by.all()
        assert match.confirmed is False

    def test_mutual_messages_confirm_and_backfill_confirmed_by(self):
        u1, u2 = self._create_two_user_prematching()
        u2_unconf = get_unconfirmed_matches(u2)
        unconf_hash = u2_unconf[0]["hash"]

        res = self._respond_to_proposed_match({"unconfirmed_match_uuid": unconf_hash, "confirm": True}, user=u2)
        res.render()
        assert res.status_code == 200

        match = Match.get_match(u1, u2).first()
        assert match is not None
        assert match.confirmed is False
        assert set(match.confirmed_by.all()) == {u2}

        from chat.helpers import create_and_deliver_message
        from chat.models import Chat

        chat = Chat.get_or_create_chat(u1, u2)
        create_and_deliver_message(
            chat=chat,
            sender=u2,
            recipient=u1,
            text="Hello from learner",
            send_websocket=False,
            send_email=False,
        )
        match.refresh_from_db()
        assert match.confirmed is False

        create_and_deliver_message(
            chat=chat,
            sender=u1,
            recipient=u2,
            text="Hello from volunteer",
            send_websocket=False,
            send_email=False,
        )
        match.refresh_from_db()
        assert match.confirmed is True
        assert set(match.confirmed_by.all()) == {u1, u2}

    def test_random_call_proposal_accept_sends_new_match_notifications(self):
        u1, u2 = self._create_two_user_prematching()
        ProposedMatch.get_proposal_between(u1, u2).delete()
        create_user_matching_proposal(
            {u1, u2},
            send_confirm_match_email=False,
            match_type=MatchType.RANDOM_CALL,
            confirming_user=u2,
        )
        proposal = get_unconfirmed_matches(u2)[0]
        for user in (u1, u2):
            user.state.searching_state = State.SearchingStateChoices.SEARCHING
            user.state.save(update_fields=["searching_state"])

        with patch.object(User, "send_email") as mock_send_email:
            res = self._respond_to_proposed_match(
                {"unconfirmed_match_uuid": proposal["hash"], "confirm": True},
                user=u2,
            )

        res.render()
        assert res.status_code == 200
        match = Match.get_match(u1, u2).first()
        assert match is not None
        assert match.match_type == MatchType.RANDOM_CALL
        u1.state.refresh_from_db()
        u2.state.refresh_from_db()
        assert u1.state.searching_state == State.SearchingStateChoices.IDLE
        assert u2.state.searching_state == State.SearchingStateChoices.IDLE

        new_match_calls = [call for call in mock_send_email.call_args_list if call.args[0] == "new-match"]
        assert len(new_match_calls) == 2
        assert {call.kwargs["match_id"] for call in new_match_calls} == {match.pk}

        auto_messages = Message.objects.filter(recipient__in=[u1, u2]).exclude(sender__in=[u1, u2])
        assert auto_messages.filter(recipient=u1).exists()
        assert auto_messages.filter(recipient=u2).exists()
