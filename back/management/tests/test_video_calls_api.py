from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from video.models import LivekitSession

from management.models.user import User


class VideoCallsListFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email="video-calls-admin@example.com",
            password="Test123!",
            first_name="Admin",
            last_name="User",
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        self.u1 = User.objects.create_user(
            email="video-calls-u1@example.com",
            password="Test123!",
            first_name="One",
            last_name="User",
        )
        self.u2 = User.objects.create_user(
            email="video-calls-u2@example.com",
            password="Test123!",
            first_name="Two",
            last_name="User",
        )
        self.normal = LivekitSession.objects.create(
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
            unusual_length=False,
        )
        self.unusual = LivekitSession.objects.create(
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
            unusual_length=True,
        )
        self.client.force_login(self.staff)

    def test_filter_schema_includes_unusual_length_list(self):
        response = self.client.get("/api/matching/video_calls/filters/")
        self.assertEqual(response.status_code, 200)
        names = [entry["name"] for entry in response.data["lists"]]
        self.assertEqual(names, ["all", "unusual_length"])
        unusual = next(entry for entry in response.data["lists"] if entry["name"] == "unusual_length")
        self.assertEqual(unusual["label"], "Unusual length")

    def test_list_unusual_length_returns_only_flagged_calls(self):
        response = self.client.get("/api/matching/video_calls/", {"list": "unusual_length"})
        self.assertEqual(response.status_code, 200)
        uuids = {row["uuid"] for row in response.data["results"]}
        self.assertEqual(uuids, {str(self.unusual.uuid)})
        self.assertTrue(response.data["results"][0]["unusual_length"])

    def test_list_all_includes_flagged_and_normal_calls(self):
        response = self.client.get("/api/matching/video_calls/", {"list": "all"})
        self.assertEqual(response.status_code, 200)
        uuids = {row["uuid"] for row in response.data["results"]}
        self.assertEqual(uuids, {str(self.normal.uuid), str(self.unusual.uuid)})

    def test_unusual_length_boolean_filter(self):
        response = self.client.get("/api/matching/video_calls/", {"unusual_length": "true"})
        self.assertEqual(response.status_code, 200)
        uuids = {row["uuid"] for row in response.data["results"]}
        self.assertEqual(uuids, {str(self.unusual.uuid)})

    def test_order_by_duration_descending_puts_the_longest_call_first(self):
        now = timezone.now()
        short = LivekitSession.create_backdated(
            created_at=now - timedelta(hours=1),
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
        )
        LivekitSession.objects.filter(pk=short.pk).update(end_time=short.created_at + timedelta(minutes=5))
        long = LivekitSession.create_backdated(
            created_at=now - timedelta(hours=3),
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
        )
        LivekitSession.objects.filter(pk=long.pk).update(end_time=long.created_at + timedelta(hours=2))

        response = self.client.get("/api/matching/video_calls/", {"order_by": "-duration"})

        self.assertEqual(response.status_code, 200)
        uuids = [row["uuid"] for row in response.data["results"]]
        self.assertLess(uuids.index(str(long.uuid)), uuids.index(str(short.uuid)))

    def test_order_by_duration_ascending_puts_the_shortest_call_first(self):
        now = timezone.now()
        short = LivekitSession.create_backdated(
            created_at=now - timedelta(hours=1),
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
        )
        LivekitSession.objects.filter(pk=short.pk).update(end_time=short.created_at + timedelta(minutes=5))
        long = LivekitSession.create_backdated(
            created_at=now - timedelta(hours=3),
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
        )
        LivekitSession.objects.filter(pk=long.pk).update(end_time=long.created_at + timedelta(hours=2))

        response = self.client.get("/api/matching/video_calls/", {"order_by": "duration"})

        self.assertEqual(response.status_code, 200)
        uuids = [row["uuid"] for row in response.data["results"]]
        self.assertLess(uuids.index(str(short.uuid)), uuids.index(str(long.uuid)))

    def test_order_by_duration_uses_elapsed_time_for_a_still_open_call(self):
        """A still-open call sorts by how long it has been open so far, not by
        dropping to the bottom/top for having no end_time."""
        now = timezone.now()
        finished = LivekitSession.create_backdated(
            created_at=now - timedelta(minutes=10),
            u1=self.u1,
            u2=self.u2,
            is_active=False,
            both_have_been_active=True,
        )
        LivekitSession.objects.filter(pk=finished.pk).update(end_time=finished.created_at + timedelta(minutes=5))
        long_open = LivekitSession.create_backdated(
            created_at=now - timedelta(hours=3),
            u1=self.u1,
            u2=self.u2,
            is_active=True,
            u1_active=True,
            both_have_been_active=True,
        )

        response = self.client.get("/api/matching/video_calls/", {"order_by": "-duration"})

        self.assertEqual(response.status_code, 200)
        uuids = [row["uuid"] for row in response.data["results"]]
        self.assertLess(uuids.index(str(long_open.uuid)), uuids.index(str(finished.uuid)))
