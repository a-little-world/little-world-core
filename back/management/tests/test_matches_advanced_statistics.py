from datetime import timedelta
from uuid import uuid4

from chat.models import Chat, Message
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from video.models import LivekitSession

from management.api.matches_advanced_statistics import (
    _activity_indices_for_matches,
    _bucket_match_rows,
    _first_message_at,
    _first_mutual_call_at,
    match_mutual_call_trend,
    match_timing_statistics,
)
from management.models.matches import Match
from management.models.user import User


class MatchStatisticsTests(TestCase):
    def _create_user(self, email_prefix: str) -> User:
        return User.objects.create_user(
            email=f"{email_prefix}-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name="User",
        )

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = match_timing_statistics
        self.staff_user = self._create_user("staff")
        self.staff_user.is_staff = True
        self.staff_user.save(update_fields=["is_staff"])
        self.user1 = self._create_user("user1")
        self.user2 = self._create_user("user2")

    def test_batch_indices_find_mutual_call_and_messages_for_match(self):
        now = timezone.now()
        match = Match.objects.create(user1=self.user1, user2=self.user2)
        Match.objects.filter(pk=match.pk).update(created_at=now - timedelta(days=10))

        call_created_at = now - timedelta(days=7)
        session = LivekitSession.objects.create(
            u1=self.user1,
            u2=self.user2,
            both_have_been_active=True,
            is_active=False,
        )
        LivekitSession.objects.filter(pk=session.pk).update(created_at=call_created_at)

        chat = Chat.get_or_create_chat(self.user1, self.user2)
        first_message = Message.objects.create(
            chat=chat,
            sender=self.user1,
            recipient=self.user2,
            text="hello",
        )
        second_message = Message.objects.create(
            chat=chat,
            sender=self.user2,
            recipient=self.user1,
            text="hi",
        )
        Message.objects.filter(pk=first_message.pk).update(created=now - timedelta(days=6))
        Message.objects.filter(pk=second_message.pk).update(created=now - timedelta(days=5))

        match_rows = [(match.id, self.user1.id, self.user2.id, now - timedelta(days=10))]
        session_index, message_index = _activity_indices_for_matches(match_rows, now - timedelta(days=20))

        assert _first_mutual_call_at(session_index, self.user1.id, self.user2.id, now - timedelta(days=10)) == (
            call_created_at
        )
        assert _first_message_at(message_index, self.user1.id, self.user2.id, now - timedelta(days=10)) == (
            now - timedelta(days=6)
        )
        assert _first_message_at(message_index, self.user2.id, self.user1.id, now - timedelta(days=10)) == (
            now - timedelta(days=5)
        )

    def test_match_timing_statistics_uses_batch_loading(self):
        now = timezone.now()
        match = Match.objects.create(user1=self.user1, user2=self.user2)
        Match.objects.filter(pk=match.pk).update(created_at=now - timedelta(days=10))

        call_created_at = now - timedelta(days=4)
        session = LivekitSession.objects.create(
            u1=self.user1,
            u2=self.user2,
            both_have_been_active=True,
            is_active=False,
        )
        LivekitSession.objects.filter(pk=session.pk).update(created_at=call_created_at)

        chat = Chat.get_or_create_chat(self.user1, self.user2)
        first_message = Message.objects.create(
            chat=chat,
            sender=self.user1,
            recipient=self.user2,
            text="hello",
        )
        second_message = Message.objects.create(
            chat=chat,
            sender=self.user2,
            recipient=self.user1,
            text="hi",
        )
        Message.objects.filter(pk=first_message.pk).update(created=now - timedelta(days=3))
        Message.objects.filter(pk=second_message.pk).update(created=now - timedelta(days=2))

        request = self.factory.post(
            "/api/matching/matches/statistics/timing/",
            {
                "start_date": (now - timedelta(days=20)).date().isoformat(),
                "end_date": now.date().isoformat(),
            },
            format="json",
        )
        force_authenticate(request, user=self.staff_user)

        response = self.view(request)

        assert response.status_code == 200
        assert response.data["total_matches"] == 1
        assert response.data["first_call_match_count"] == 1
        assert response.data["both_messaged_match_count"] == 1
        assert response.data["average_days_to_first_call"] == 6.0
        assert response.data["median_days_to_first_call"] == 6.0
        assert response.data["average_days_until_both_messaged"] == 7.0
        assert response.data["median_days_until_both_messaged"] == 7.0

    def test_bucket_match_rows_handles_timezone_aware_created_at(self):
        now = timezone.now()
        match_rows = [(1, 10, 20, now)]
        bucket_start = now.date()
        bucket_end = now.date()

        assert _bucket_match_rows(match_rows, bucket_start, bucket_end) == match_rows

    def test_mutual_call_trend_returns_weekly_buckets(self):
        now = timezone.now()
        match = Match.objects.create(user1=self.user1, user2=self.user2)
        Match.objects.filter(pk=match.pk).update(created_at=now - timedelta(days=30))

        session = LivekitSession.objects.create(
            u1=self.user1,
            u2=self.user2,
            both_have_been_active=True,
            is_active=False,
        )
        LivekitSession.objects.filter(pk=session.pk).update(created_at=now - timedelta(days=29))

        request = self.factory.post(
            "/api/matching/matches/statistics/mutual-call-trend/",
            {
                "start_date": (now - timedelta(days=60)).date().isoformat(),
                "end_date": now.date().isoformat(),
                "bucket_size": 7,
            },
            format="json",
        )
        force_authenticate(request, user=self.staff_user)

        response = match_mutual_call_trend(request)

        assert response.status_code == 200
        assert isinstance(response.data, list)
        assert response.data
        assert any(point["mutual_call_match_count"] == 1 for point in response.data)
