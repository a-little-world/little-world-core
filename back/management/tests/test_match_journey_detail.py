"""Admin match-detail extras: qualifying-session calls, week grid, server streaks."""

from datetime import timedelta
from uuid import uuid4

from chat.models import Chat, Message
from django.test import TestCase
from video.models import LivekitSession

from management.analytics.match_journey.detail import (
    DESIRED_DURATION_WEEKS,
    current_week,
    match_journey_stages,
    match_stats_retrieve_extra,
    match_weekly_activity_details,
    match_weekly_activity_retrieve_extra,
    week_bounds,
)
from management.models.matches import Match
from management.models.user import User


def _user(label: str) -> User:
    return User.objects.create_user(
        email=f"{label}-{uuid4()}@example.com",
        password="Test123!",
        first_name=label.title(),
        last_name="User",
    )


class MatchJourneyDetailTests(TestCase):
    def setUp(self):
        self.user1 = _user("learner")
        self.user2 = _user("volunteer")
        self.match = Match.objects.create(user1=self.user1, user2=self.user2)

    def _qualifying_call(self, *, start, duration=timedelta(minutes=30)):
        session = LivekitSession.objects.create(
            u1=self.user1, u2=self.user2, both_have_been_active=True, is_active=False
        )
        LivekitSession.objects.filter(pk=session.pk).update(
            created_at=start,
            end_time=start + duration,
        )
        return session

    def test_empty_match_stats_are_null(self):
        self.assertEqual(
            match_stats_retrieve_extra(self.match),
            {
                "last_video_call_at": None,
                "user1_last_message_at": None,
                "user2_last_message_at": None,
                "qualifying_video_call_count": 0,
                "average_video_call_duration_seconds": None,
                "median_video_call_duration_seconds": None,
                "total_video_call_duration_seconds": None,
            },
        )

    def test_stats_average_median_total_for_qualifying_calls(self):
        start = self.match.created_at + timedelta(hours=1)
        self._qualifying_call(start=start, duration=timedelta(minutes=30))
        self._qualifying_call(start=start + timedelta(hours=1), duration=timedelta(minutes=20))

        stats = match_stats_retrieve_extra(self.match)
        self.assertEqual(stats["qualifying_video_call_count"], 2)
        self.assertEqual(stats["average_video_call_duration_seconds"], 1500)
        self.assertEqual(stats["median_video_call_duration_seconds"], 1500)
        self.assertEqual(stats["total_video_call_duration_seconds"], 3000)
        self.assertIsNotNone(stats["last_video_call_at"])

    def test_stats_ignore_sessions_that_never_ended(self):
        LivekitSession.objects.create(u1=self.user1, u2=self.user2, both_have_been_active=True, is_active=True)

        stats = match_stats_retrieve_extra(self.match)
        self.assertEqual(stats["qualifying_video_call_count"], 0)
        self.assertIsNone(stats["last_video_call_at"])
        self.assertIsNone(stats["total_video_call_duration_seconds"])

    def test_sessions_before_match_creation_do_not_count(self):
        self._qualifying_call(start=self.match.created_at - timedelta(days=1))

        self.assertEqual(match_stats_retrieve_extra(self.match)["qualifying_video_call_count"], 0)
        week1 = match_weekly_activity_retrieve_extra(self.match, as_of=self.match.created_at + timedelta(days=1))[
            "journey"
        ]["weekly_activity"][0]
        self.assertEqual(week1["video_calls"], 0)

    def test_one_sided_sessions_do_not_count(self):
        start = self.match.created_at + timedelta(hours=1)
        session = LivekitSession.objects.create(
            u1=self.user1, u2=self.user2, both_have_been_active=False, is_active=False
        )
        LivekitSession.objects.filter(pk=session.pk).update(
            created_at=start,
            end_time=start + timedelta(minutes=30),
        )

        self.assertEqual(match_stats_retrieve_extra(self.match)["qualifying_video_call_count"], 0)
        week1 = match_weekly_activity_retrieve_extra(self.match, as_of=self.match.created_at + timedelta(days=1))[
            "journey"
        ]["weekly_activity"][0]
        self.assertEqual(week1["video_calls"], 0)

    def test_weekly_activity_empty_match_has_planned_weeks_only(self):
        as_of = self.match.created_at + timedelta(days=3)
        payload = match_weekly_activity_retrieve_extra(self.match, as_of=as_of)
        journey = payload["journey"]

        self.assertEqual(journey["current_week"], 1)
        self.assertEqual(journey["desired_duration_weeks"], DESIRED_DURATION_WEEKS)
        self.assertFalse(journey["is_free_play"])
        self.assertEqual(len(journey["weekly_activity"]), DESIRED_DURATION_WEEKS)
        self.assertTrue(journey["weekly_activity"][0]["is_current_week"])
        self.assertFalse(journey["weekly_activity"][0]["is_free_play_week"])
        self.assertEqual(journey["weekly_activity"][0]["messages"], 0)
        self.assertEqual(journey["weekly_activity"][0]["video_calls"], 0)
        self.assertEqual(journey["stages"][0]["id"], "matched")
        self.assertEqual(journey["active_stage_index"], 1)
        self.assertEqual(
            [stage["id"] for stage in journey["stages"]],
            [
                "matched",
                "first_call",
                "in_flight",
                "success",
                "engaged",
            ],
        )
        self.assertEqual(journey["stages"][2]["description"], "0 of 8 tokens")
        self.assertFalse(journey["stages"][3]["achieved"])
        self.assertEqual(
            journey["streaks"]["video_calls"],
            {"current": 0, "record": 0, "record_start_week": None, "record_end_week": None},
        )

    def test_weekly_activity_counts_messages_per_user_and_qualifying_calls(self):
        match_start = self.match.created_at
        chat = Chat.get_or_create_chat(self.user1, self.user2)
        first = Message.objects.create(chat=chat, sender=self.user1, recipient=self.user2, text="hi")
        second = Message.objects.create(chat=chat, sender=self.user2, recipient=self.user1, text="yo")
        Message.objects.filter(pk=first.pk).update(created=match_start + timedelta(days=1))
        Message.objects.filter(pk=second.pk).update(created=match_start + timedelta(days=2))
        self._qualifying_call(start=match_start + timedelta(days=3))

        as_of = match_start + timedelta(days=4)
        week1 = match_weekly_activity_retrieve_extra(self.match, as_of=as_of)["journey"]["weekly_activity"][0]
        self.assertEqual(week1["messages"], 2)
        self.assertEqual(week1["messages_user1"], 1)
        self.assertEqual(week1["messages_user2"], 1)
        self.assertEqual(week1["video_calls"], 1)

    def test_unterminated_calls_do_not_count_in_week_grid_or_stats(self):
        session = LivekitSession.objects.create(
            u1=self.user1, u2=self.user2, both_have_been_active=True, is_active=True
        )
        LivekitSession.objects.filter(pk=session.pk).update(created_at=self.match.created_at + timedelta(hours=1))

        week1 = match_weekly_activity_retrieve_extra(self.match, as_of=self.match.created_at + timedelta(days=1))[
            "journey"
        ]["weekly_activity"][0]
        self.assertEqual(week1["video_calls"], 0)
        self.assertEqual(match_stats_retrieve_extra(self.match)["qualifying_video_call_count"], 0)

    def test_week_grid_and_stats_agree_on_call_count(self):
        start = self.match.created_at + timedelta(hours=1)
        self._qualifying_call(start=start)
        self._qualifying_call(start=start + timedelta(hours=2), duration=timedelta(minutes=10))

        as_of = self.match.created_at + timedelta(days=1)
        week1_calls = match_weekly_activity_retrieve_extra(self.match, as_of=as_of)["journey"]["weekly_activity"][0][
            "video_calls"
        ]
        self.assertEqual(week1_calls, match_stats_retrieve_extra(self.match)["qualifying_video_call_count"])
        self.assertEqual(week1_calls, 2)

    def _message_in_week(self, chat, *, offset_days: int):
        message = Message.objects.create(chat=chat, sender=self.user1, recipient=self.user2, text="m")
        Message.objects.filter(pk=message.pk).update(created=self.match.created_at + timedelta(days=offset_days))

    def test_empty_current_week_does_not_break_the_streak(self):
        """Week 3 is still running, so a two-week run is still a two-week run."""
        chat = Chat.get_or_create_chat(self.user1, self.user2)
        self._message_in_week(chat, offset_days=1)
        self._message_in_week(chat, offset_days=8)

        as_of = self.match.created_at + timedelta(days=15)  # week 3, nothing in it yet
        streaks = match_weekly_activity_retrieve_extra(self.match, as_of=as_of)["journey"]["streaks"]["messages"]
        self.assertEqual(streaks["current"], 2)
        self.assertEqual(streaks["record"], 2)
        self.assertEqual(streaks["record_start_week"], 1)
        self.assertEqual(streaks["record_end_week"], 2)

    def test_streaks_record_longest_run_and_current_breaks_on_completed_empty_week(self):
        chat = Chat.get_or_create_chat(self.user1, self.user2)
        self._message_in_week(chat, offset_days=1)
        self._message_in_week(chat, offset_days=8)
        self._message_in_week(chat, offset_days=22)  # week 4; week 3 elapsed with nothing

        as_of = self.match.created_at + timedelta(days=29)  # week 5
        streaks = match_weekly_activity_retrieve_extra(self.match, as_of=as_of)["journey"]["streaks"]["messages"]
        self.assertEqual(streaks["current"], 1)
        self.assertEqual(streaks["record"], 2)
        self.assertEqual(streaks["record_start_week"], 1)
        self.assertEqual(streaks["record_end_week"], 2)

    def test_call_streak_current_includes_current_week_when_active(self):
        match_start = self.match.created_at
        self._qualifying_call(start=match_start + timedelta(days=1))
        self._qualifying_call(start=match_start + timedelta(days=8))

        as_of = match_start + timedelta(days=10)  # week 2
        streaks = match_weekly_activity_retrieve_extra(self.match, as_of=as_of)["journey"]["streaks"]["video_calls"]
        self.assertEqual(streaks["current"], 2)
        self.assertEqual(streaks["record"], 2)
        self.assertEqual(streaks["record_start_week"], 1)
        self.assertEqual(streaks["record_end_week"], 2)

    def test_free_play_week_after_planned_duration(self):
        as_of = self.match.created_at + timedelta(weeks=DESIRED_DURATION_WEEKS, days=1)
        journey = match_weekly_activity_retrieve_extra(self.match, as_of=as_of)["journey"]
        self.assertEqual(journey["current_week"], DESIRED_DURATION_WEEKS + 1)
        self.assertTrue(journey["is_free_play"])
        self.assertTrue(journey["weekly_activity"][-1]["is_free_play_week"])
        self.assertEqual(len(journey["weekly_activity"]), DESIRED_DURATION_WEEKS + 1)

    def test_stages_mark_off_platform_as_success(self):
        marked_at = self.match.created_at + timedelta(days=12)
        self.match.completed_off_plattform = True
        self.match.completed_off_plattform_auto_marked_at = marked_at
        self.match.latest_interaction_at = marked_at
        self.match.save(
            update_fields=[
                "completed_off_plattform",
                "completed_off_plattform_auto_marked_at",
                "latest_interaction_at",
            ]
        )
        stages = match_journey_stages(self.match, as_of=marked_at + timedelta(days=2))
        ids = [stage["id"] for stage in stages["stages"]]
        self.assertEqual(ids, ["matched", "first_call", "in_flight", "success", "engaged"])
        success = stages["stages"][3]
        self.assertTrue(success["achieved"])
        self.assertIn(marked_at.date().isoformat(), success["achieved_at"])
        self.assertEqual(stages["active_stage_index"], 4)

    def test_stages_show_token_progress_on_in_flight(self):
        start = self.match.created_at + timedelta(hours=1)
        self._qualifying_call(start=start, duration=timedelta(minutes=30))
        self.match.first_interaction_at = start
        self.match.latest_interaction_at = start
        self.match.total_mutal_video_calls_counter = 1
        self.match.save(
            update_fields=[
                "first_interaction_at",
                "latest_interaction_at",
                "total_mutal_video_calls_counter",
            ]
        )
        stages = match_journey_stages(self.match, as_of=start + timedelta(days=1))
        in_flight = next(stage for stage in stages["stages"] if stage["id"] == "in_flight")
        self.assertTrue(in_flight["achieved"])
        self.assertEqual(in_flight["description"], "1 of 8 tokens")
        self.assertEqual(stages["stages"][3]["id"], "success")
        self.assertFalse(stages["stages"][3]["achieved"])
        # First unachieved step: matched / first call / in-flight are all done.
        self.assertEqual(stages["active_stage_index"], 3)

    def test_stages_success_date_is_the_call_that_crossed_the_threshold(self):
        start = self.match.created_at + timedelta(hours=1)
        self._qualifying_call(start=start, duration=timedelta(minutes=210))
        success_at = start + timedelta(minutes=210)
        self.match.first_interaction_at = start
        self.match.latest_interaction_at = success_at
        self.match.save(update_fields=["first_interaction_at", "latest_interaction_at"])

        stages = match_journey_stages(self.match, as_of=success_at + timedelta(days=1))
        success = stages["stages"][3]
        self.assertEqual(success["id"], "success")
        self.assertTrue(success["achieved"])
        self.assertIn(success_at.date().isoformat(), success["achieved_at"])
        self.assertEqual(stages["stages"][4]["id"], "engaged")
        self.assertEqual(stages["active_stage_index"], 4)

    def test_stages_dormant_after_success_when_activity_is_older_than_four_weeks(self):
        start = self.match.created_at + timedelta(hours=1)
        self._qualifying_call(start=start, duration=timedelta(minutes=210))
        last_activity = start + timedelta(minutes=210)
        self.match.first_interaction_at = start
        self.match.latest_interaction_at = last_activity
        self.match.save(update_fields=["first_interaction_at", "latest_interaction_at"])

        stages = match_journey_stages(self.match, as_of=last_activity + timedelta(days=29))
        self.assertEqual(stages["stages"][3]["id"], "success")
        dormant = stages["stages"][4]
        self.assertEqual(dormant["id"], "dormant")
        self.assertTrue(dormant["achieved"])
        self.assertIn(last_activity.date().isoformat(), dormant["achieved_at"])

    def test_stages_failure_after_ten_weeks_marks_the_step_it_stalled_at(self):
        """A match that never called stalls at `first_call`, and the failure says so there.

        No separate "Match failure" step: the stepper renders every step before the active
        one as complete, so a failure step achieved after unreached ones ticked a first
        call that never happened.
        """
        last_activity = self.match.created_at + timedelta(days=3)
        self.match.latest_interaction_at = last_activity
        self.match.save(update_fields=["latest_interaction_at"])
        stages = match_journey_stages(self.match, as_of=last_activity + timedelta(days=71))

        self.assertEqual(stages["active_stage_index"], 1)
        stalled = stages["stages"][1]
        self.assertEqual(stalled["id"], "first_call")
        self.assertFalse(stalled["achieved"])
        self.assertTrue(stalled["failed"])
        self.assertIsNotNone(stalled["failed_at"])
        self.assertEqual(stalled["description"], "No activity for 10 weeks before reaching success.")
        # Nothing later is claimed, and no step is invented for the failure.
        self.assertNotIn("failure", [stage["id"] for stage in stages["stages"]])
        self.assertFalse(any(stage["achieved"] for stage in stages["stages"][2:]))

    def test_stages_never_mark_an_unreached_step_complete(self):
        """The stepper completes every step before the active one, so the run must be contiguous."""
        last_activity = self.match.created_at + timedelta(days=3)
        self.match.latest_interaction_at = last_activity
        self.match.save(update_fields=["latest_interaction_at"])
        stages = match_journey_stages(self.match, as_of=last_activity + timedelta(days=71))

        active = stages["active_stage_index"]
        self.assertTrue(all(stage["achieved"] for stage in stages["stages"][:active]))

    def test_closed_successful_match_still_reports_being_closed(self):
        """`is_closed` describes the match, not the outcome — both can be true at once."""
        start = self.match.created_at + timedelta(hours=1)
        self._qualifying_call(start=start, duration=timedelta(minutes=210))
        self.match.active = False
        self.match.latest_interaction_at = start + timedelta(minutes=210)
        self.match.report_unmatch = [{"kind": "unmatch", "reason": "Wrapped up", "time": "2026-04-01T12:00:00Z"}]
        self.match.save(update_fields=["active", "report_unmatch", "latest_interaction_at"])

        stages = match_journey_stages(self.match, as_of=self.match.created_at + timedelta(days=3))
        self.assertTrue(stages["stages"][3]["achieved"], "expected the success step to be reached")
        self.assertTrue(stages["is_closed"])
        self.assertEqual(stages["closed_kind"], "unmatch")

    def test_stages_unmatch_marks_the_stalled_step_not_a_sixth_closed_step(self):
        self.match.active = False
        self.match.latest_interaction_at = self.match.created_at + timedelta(days=2)
        self.match.report_unmatch = [
            {
                "kind": "unmatch",
                "reason": "Not a fit",
                "time": "2026-04-01T12:00:00Z",
            }
        ]
        self.match.save(update_fields=["active", "report_unmatch", "latest_interaction_at"])
        stages = match_journey_stages(self.match, as_of=self.match.created_at + timedelta(days=3))
        self.assertTrue(stages["is_closed"])
        self.assertEqual(stages["closed_kind"], "unmatch")
        ids = [stage["id"] for stage in stages["stages"]]
        self.assertEqual(len(ids), 5)
        self.assertNotIn("closed", ids)
        self.assertNotIn("failure", ids)
        stalled = stages["stages"][stages["active_stage_index"]]
        self.assertEqual(stalled["id"], "first_call")
        self.assertTrue(stalled["failed"])
        self.assertEqual(stalled["description"], "Not a fit")

    def test_week_details_returns_qualifying_calls_and_messages_oldest_first(self):
        match_start = self.match.created_at
        chat = Chat.get_or_create_chat(self.user1, self.user2)
        first = Message.objects.create(chat=chat, sender=self.user1, recipient=self.user2, text="first")
        second = Message.objects.create(chat=chat, sender=self.user2, recipient=self.user1, text="second")
        Message.objects.filter(pk=first.pk).update(created=match_start + timedelta(days=1))
        Message.objects.filter(pk=second.pk).update(created=match_start + timedelta(days=2))
        self._qualifying_call(start=match_start + timedelta(days=3), duration=timedelta(minutes=30))

        details = match_weekly_activity_details(self.match, 1)
        self.assertEqual(details["week"], 1)
        self.assertEqual([row["sender_id"] for row in details["messages"]], [self.user1.id, self.user2.id])
        self.assertEqual(details["messages"][0]["sender_name"], "Learner")
        self.assertEqual(len(details["video_calls"]), 1)
        self.assertEqual(details["video_calls"][0]["duration_seconds"], 1800)
        self.assertIsNotNone(details["video_calls"][0]["end_time"])

    def test_week_details_omit_unterminated_calls(self):
        session = LivekitSession.objects.create(
            u1=self.user1, u2=self.user2, both_have_been_active=True, is_active=True
        )
        LivekitSession.objects.filter(pk=session.pk).update(created_at=self.match.created_at + timedelta(days=1))

        details = match_weekly_activity_details(self.match, 1)
        self.assertEqual(details["video_calls"], [])

    def test_week_bounds_reject_week_below_one(self):
        with self.assertRaises(ValueError):
            week_bounds(self.match, 0)

    def test_current_week_is_one_indexed_from_created_at(self):
        created = self.match.created_at
        self.assertEqual(current_week(self.match, as_of=created + timedelta(days=6)), 1)
        self.assertEqual(current_week(self.match, as_of=created + timedelta(days=7)), 2)
