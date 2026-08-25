"""Public Match Overview: participant-only snapshot + qualifying call history."""

from datetime import timedelta
from unittest import mock
from uuid import uuid4

from chat.models import Chat, Message
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from video.models import LivekitSession

from management.analytics.match_journey.queries.activity import DESIRED_DURATION_WEEKS
from management.api.match_overview import match_overview
from management.match_success import success_token_threshold
from management.models.matches import Match
from management.models.profile import Profile
from management.models.unconfirmed_matches import MatchType
from management.models.user import User
from management.permissions import ManagementPermission

#: Distinguishes "caller did not say" from "the session genuinely has no initiator".
_UNSET = object()


def _user(label: str) -> User:
    return User.objects.create_user(
        email=f"{label}-{uuid4()}@example.com",
        password="Test123!",
        first_name=label.title(),
        last_name="User",
    )


class MatchOverviewApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user1 = _user("learner")
        self.user2 = _user("volunteer")
        self.outsider = _user("outsider")
        # A real match is a learner and a volunteer, and the operator view depends on
        # which is which — `Profile.user_type` defaults to learner for both otherwise.
        Profile.objects.filter(user=self.user2).update(user_type=Profile.TypeChoices.VOLUNTEER)
        self.match = Match.objects.create(user1=self.user1, user2=self.user2)

    def _get(self, user, *, match=None, as_of=None, params=None):
        """Call the view, optionally with the clock moved to ``as_of``.

        The view takes no ``as_of`` input — see ``match_overview`` — so tests move
        ``timezone.now`` instead of asking the endpoint to time-travel for them.
        """
        match = match or self.match
        request = self.factory.get(f"/api/matches/{match.uuid}/overview", params or {})
        if user is not None:
            force_authenticate(request, user=user)
        if as_of is None:
            return match_overview(request, match_uuid=match.uuid)
        with mock.patch("django.utils.timezone.now", return_value=as_of):
            return match_overview(request, match_uuid=match.uuid)

    def _qualifying_call(self, *, start, duration=timedelta(minutes=30), initiator=_UNSET):
        session = LivekitSession.objects.create(
            u1=self.user1,
            u2=self.user2,
            both_have_been_active=True,
            is_active=False,
            first_active_user=self.user1 if initiator is _UNSET else initiator,
        )
        LivekitSession.objects.filter(pk=session.pk).update(
            created_at=start,
            end_time=start + duration,
        )
        return LivekitSession.objects.get(pk=session.pk)

    def test_unauthenticated_is_rejected(self):
        response = self._get(user=None)
        self.assertEqual(response.status_code, 403)

    def test_non_participant_gets_404(self):
        response = self._get(self.outsider)
        self.assertEqual(response.status_code, 404)

    def test_staff_can_view_without_being_a_participant(self):
        staff = _user("admin")
        User.objects.filter(pk=staff.pk).update(is_staff=True)
        staff.refresh_from_db()

        response = self._get(staff)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["self"]["id"], str(self.user2.uuid))
        self.assertEqual(response.data["partner"]["id"], str(self.user1.uuid))

    def test_matching_user_can_view_without_being_a_participant(self):
        matcher = _user("matcher")
        content_type = ContentType.objects.get(app_label="management", model="state")
        permission, _ = Permission.objects.get_or_create(
            codename=ManagementPermission.MATCHING_USER.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.MATCHING_USER.codename},
        )
        matcher.user_permissions.add(permission)

        response = self._get(matcher)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["self"]["id"], str(self.user2.uuid))
        self.assertEqual(response.data["partner"]["id"], str(self.user1.uuid))

    def test_staff_sees_call_direction_as_the_volunteer(self):
        """The learner placed the call, so the volunteer — and the operator — see it incoming."""
        staff = _user("admin")
        User.objects.filter(pk=staff.pk).update(is_staff=True)
        staff.refresh_from_db()
        self._qualifying_call(start=self.match.created_at + timedelta(hours=1), initiator=self.user1)

        response = self._get(staff, as_of=self.match.created_at + timedelta(days=1))
        self.assertEqual(response.data["calls"][0]["direction"], "incoming")

    def test_participant_payload_names_the_partner(self):
        response = self._get(self.user1)
        self.assertEqual(response.data["partner"]["id"], str(self.user2.uuid))
        self.assertEqual(response.data["self"]["id"], str(self.user1.uuid))
        self.assertEqual(response.data["partner"]["first_name"], "Volunteer")

    def test_temporary_match_is_hidden(self):
        temp = Match.objects.create(
            user1=self.user1,
            user2=self.user2,
            match_type=MatchType.TEMPORARY,
        )
        response = self._get(self.user1, match=temp)
        self.assertEqual(response.status_code, 404)

    def test_temporary_match_is_hidden_from_staff(self):
        staff = _user("admin")
        User.objects.filter(pk=staff.pk).update(is_staff=True)
        staff.refresh_from_db()
        temp = Match.objects.create(
            user1=self.user1,
            user2=self.user2,
            match_type=MatchType.TEMPORARY,
        )
        response = self._get(staff, match=temp)
        self.assertEqual(response.status_code, 404)

    def test_empty_match_snapshot(self):
        as_of = self.match.created_at + timedelta(days=3)
        response = self._get(self.user1, as_of=as_of)
        self.assertEqual(response.status_code, 200)
        snapshot = response.data["snapshot"]
        self.assertEqual(snapshot["match_uuid"], str(self.match.uuid))
        self.assertEqual(snapshot["current_week"], 1)
        self.assertEqual(snapshot["active_weeks"], 0)
        self.assertEqual(snapshot["cycle_weeks"], DESIRED_DURATION_WEEKS)
        self.assertFalse(snapshot["is_free_play"])
        self.assertEqual(snapshot["calls"], 0)
        self.assertEqual(snapshot["total_minutes"], 0.0)
        self.assertEqual(snapshot["messages"], 0)
        self.assertEqual(snapshot["streak_weeks"], 0)
        self.assertIsNone(snapshot["last_call_at"])
        self.assertEqual(snapshot["tokens"], 0)
        self.assertEqual(snapshot["token_threshold"], success_token_threshold())
        self.assertEqual(response.data["calls"], [])

    def test_qualifying_calls_newest_first_and_direction_flips_by_viewer(self):
        start = self.match.created_at + timedelta(hours=1)
        older = self._qualifying_call(start=start, duration=timedelta(minutes=20), initiator=self.user2)
        newer = self._qualifying_call(
            start=start + timedelta(hours=2), duration=timedelta(minutes=40), initiator=self.user1
        )

        as_of = self.match.created_at + timedelta(days=1)
        as_user1 = self._get(self.user1, as_of=as_of)
        as_user2 = self._get(self.user2, as_of=as_of)

        self.assertEqual(as_user1.status_code, 200)
        snapshot = as_user1.data["snapshot"]
        self.assertEqual(snapshot["calls"], 2)
        self.assertEqual(snapshot["total_minutes"], 60.0)
        self.assertEqual(snapshot["tokens"], 2)
        self.assertEqual(as_user1.data["snapshot"], as_user2.data["snapshot"])

        calls = as_user1.data["calls"]
        self.assertEqual([row["uuid"] for row in calls], [str(newer.uuid), str(older.uuid)])
        self.assertEqual(calls[0]["duration_seconds"], 2400)
        self.assertEqual(calls[0]["direction"], "outgoing")
        self.assertEqual(calls[1]["direction"], "incoming")
        self.assertNotIn("both_participated", calls[0])

        partner_calls = as_user2.data["calls"]
        self.assertEqual(partner_calls[0]["direction"], "incoming")
        self.assertEqual(partner_calls[1]["direction"], "outgoing")

    def test_one_sided_and_unterminated_sessions_are_excluded(self):
        start = self.match.created_at + timedelta(hours=1)
        one_sided = LivekitSession.objects.create(
            u1=self.user1, u2=self.user2, both_have_been_active=False, is_active=False
        )
        LivekitSession.objects.filter(pk=one_sided.pk).update(created_at=start, end_time=start + timedelta(minutes=30))
        LivekitSession.objects.create(u1=self.user1, u2=self.user2, both_have_been_active=True, is_active=True)
        self._qualifying_call(start=start + timedelta(hours=1))

        response = self._get(self.user1, as_of=self.match.created_at + timedelta(days=1))
        self.assertEqual(response.data["snapshot"]["calls"], 1)
        self.assertEqual(len(response.data["calls"]), 1)

    def test_streak_weeks_is_video_call_current_streak(self):
        match_start = self.match.created_at
        self._qualifying_call(start=match_start + timedelta(days=1))
        self._qualifying_call(start=match_start + timedelta(days=8))
        as_of = match_start + timedelta(days=10)
        response = self._get(self.user1, as_of=as_of)
        self.assertEqual(response.data["snapshot"]["current_week"], 2)
        self.assertEqual(response.data["snapshot"]["streak_weeks"], 2)

    def test_free_play_after_planned_duration(self):
        as_of = self.match.created_at + timedelta(weeks=DESIRED_DURATION_WEEKS, days=1)
        response = self._get(self.user1, as_of=as_of)
        self.assertEqual(response.data["snapshot"]["current_week"], DESIRED_DURATION_WEEKS + 1)
        self.assertTrue(response.data["snapshot"]["is_free_play"])

    def test_messages_count_pair_chat(self):
        chat = Chat.get_or_create_chat(self.user1, self.user2)
        Message.objects.create(chat=chat, sender=self.user1, recipient=self.user2, text="hi")
        Message.objects.create(chat=chat, sender=self.user2, recipient=self.user1, text="yo")
        response = self._get(self.user1, as_of=self.match.created_at + timedelta(days=1))
        self.assertEqual(response.data["snapshot"]["messages"], 2)

    def test_messages_before_the_match_still_count(self):
        """Messages are pair-lifetime by decision, unlike calls. See ``queries/activity``."""
        chat = Chat.get_or_create_chat(self.user1, self.user2)
        message = Message.objects.create(
            chat=chat, sender=self.user1, recipient=self.user2, text="met on a random call"
        )
        Message.objects.filter(pk=message.pk).update(created=self.match.created_at - timedelta(days=5))

        response = self._get(self.user1, as_of=self.match.created_at + timedelta(days=1))
        self.assertEqual(response.data["snapshot"]["messages"], 1)

    def test_call_without_recorded_initiator_is_unknown_for_both_viewers(self):
        self._qualifying_call(start=self.match.created_at + timedelta(hours=1), initiator=None)
        as_of = self.match.created_at + timedelta(days=1)

        for viewer in (self.user1, self.user2):
            with self.subTest(viewer=viewer.pk):
                response = self._get(viewer, as_of=as_of)
                self.assertEqual(response.data["calls"][0]["direction"], "unknown")

    def test_as_of_query_param_is_ignored(self):
        """The clock is not caller-controlled: a stale week would change what the page claims."""
        far_future = (self.match.created_at + timedelta(weeks=52)).isoformat()
        response = self._get(self.user1, as_of=self.match.created_at + timedelta(days=1), params={"as_of": far_future})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["snapshot"]["current_week"], 1)

    def test_active_weeks_counts_weeks_with_calls_not_elapsed_weeks(self):
        """The cycle is ten weeks of calling, so gaps cost nothing but an unbanked week."""
        match_start = self.match.created_at
        self._qualifying_call(start=match_start + timedelta(days=1))  # week 1
        self._qualifying_call(start=match_start + timedelta(days=3))  # week 1 again
        self._qualifying_call(start=match_start + timedelta(days=22))  # week 4; 2 and 3 idle

        as_of = match_start + timedelta(days=29)  # week 5
        snapshot = self._get(self.user1, as_of=as_of).data["snapshot"]
        self.assertEqual(snapshot["current_week"], 5)
        self.assertEqual(snapshot["active_weeks"], 2)

    def test_active_weeks_ignores_messages(self):
        chat = Chat.get_or_create_chat(self.user1, self.user2)
        Message.objects.create(chat=chat, sender=self.user1, recipient=self.user2, text="hi")

        snapshot = self._get(self.user1, as_of=self.match.created_at + timedelta(days=1)).data["snapshot"]
        self.assertEqual(snapshot["messages"], 1)
        self.assertEqual(snapshot["active_weeks"], 0)

    def test_empty_current_week_does_not_break_the_streak(self):
        """Week 3 is still running, so an eight-week runner does not read 0 on a Monday."""
        match_start = self.match.created_at
        self._qualifying_call(start=match_start + timedelta(days=1))
        self._qualifying_call(start=match_start + timedelta(days=8))
        as_of = match_start + timedelta(days=15)  # week 3, nothing in it yet

        response = self._get(self.user1, as_of=as_of)
        self.assertEqual(response.data["snapshot"]["current_week"], 3)
        self.assertEqual(response.data["snapshot"]["streak_weeks"], 2)

    def test_completed_empty_week_still_breaks_the_streak(self):
        match_start = self.match.created_at
        self._qualifying_call(start=match_start + timedelta(days=1))
        self._qualifying_call(start=match_start + timedelta(days=15))  # week 3; week 2 empty
        as_of = match_start + timedelta(days=22)  # week 4

        response = self._get(self.user1, as_of=as_of)
        self.assertEqual(response.data["snapshot"]["current_week"], 4)
        self.assertEqual(response.data["snapshot"]["streak_weeks"], 1)

    def test_chat_id_prefers_the_chat_holding_the_messages(self):
        """A temporary random-call chat is not the chat the pair can open."""
        older = Chat.get_or_create_chat(self.user1, self.user2)
        Message.objects.create(chat=older, sender=self.user1, recipient=self.user2, text="hi")
        newer = Chat.objects.create(u1=self.user2, u2=self.user1, is_temporary=True)

        response = self._get(self.user1)
        self.assertEqual(response.data["chat_id"], str(older.uuid))
        self.assertNotEqual(response.data["chat_id"], str(newer.uuid))

    def test_chat_id_skips_a_temporary_chat_when_neither_has_messages(self):
        Chat.objects.create(u1=self.user1, u2=self.user2)
        temporary = Chat.objects.create(u1=self.user2, u2=self.user1, is_temporary=True)

        response = self._get(self.user1)
        self.assertNotEqual(response.data["chat_id"], str(temporary.uuid))

    def test_chat_id_is_null_when_the_pair_have_no_chat(self):
        response = self._get(self.user1)
        self.assertIsNone(response.data["chat_id"])

    def test_support_match_is_visible_to_participant(self):
        support = Match.objects.create(user1=self.user1, user2=self.user2, support_matching=True)
        response = self._get(self.user1, match=support)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["snapshot"]["match_uuid"], str(support.uuid))
