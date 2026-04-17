from unittest.mock import patch

from django.test import TestCase, override_settings


class TestCalcomWebhookCallback(TestCase):
    @override_settings(DJ_CALCOM_QUERY_ACCESS_PARAM="test-secret")
    @patch("management.api.calcom.get_user_by_hash")
    def test_meeting_ended_without_payload_does_not_raise(self, mock_get_user_by_hash):
        webhook_body = {
            "triggerEvent": "MEETING_ENDED",
            "id": 123456,
            "title": "Meeting ended event without payload",
        }

        response = self.client.post(
            "/api/calcom/?secret=test-secret",
            data=webhook_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        mock_get_user_by_hash.assert_not_called()

    @override_settings(DJ_CALCOM_QUERY_ACCESS_PARAM="test-secret")
    @patch("management.api.calcom.get_user_by_hash")
    def test_booking_created_without_payload_does_not_raise(self, mock_get_user_by_hash):
        webhook_body = {
            "triggerEvent": "BOOKING_CREATED",
            "id": 123456,
            "title": "Booking created without payload",
        }

        response = self.client.post(
            "/api/calcom/?secret=test-secret",
            data=webhook_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        mock_get_user_by_hash.assert_not_called()
