import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from management.api.calcom import (
    _extract_attendee_nested_response,
    _extract_query_param_from_url,
    _extract_user_field_value,
)


class TestCalcomFieldExtraction(TestCase):
    def test_extracts_uuid_from_user_fields_responses(self):
        payload = {"userFieldsResponses": {"uuid": {"value": "user-uuid"}}}
        self.assertEqual(_extract_user_field_value(payload, "uuid"), "user-uuid")

    def test_extracts_uuid_from_responses(self):
        payload = {"responses": {"uuid": {"value": "user-uuid"}}}
        self.assertEqual(_extract_user_field_value(payload, "uuid"), "user-uuid")

    def test_extracts_uuid_from_custom_inputs(self):
        payload = {"customInputs": {"uuid": "user-uuid"}}
        self.assertEqual(_extract_user_field_value(payload, "uuid"), "user-uuid")

    def test_extracts_uuid_from_metadata(self):
        payload = {"metadata": {"uuid": "user-uuid"}}
        self.assertEqual(_extract_user_field_value(payload, "uuid"), "user-uuid")

    def test_extracts_query_param_from_url(self):
        url = "https://example.com/path?uuid=user-uuid&bookingcode=abc"
        self.assertEqual(_extract_query_param_from_url(url, "uuid"), "user-uuid")

    def test_extracts_bookingcode_from_attendee_nested_responses(self):
        payload = {
            "attendees": [
                {
                    "bookingSeat": {
                        "data": {
                            "responses": {
                                "bookingcode": "booking-123",
                            }
                        }
                    }
                }
            ]
        }
        self.assertEqual(_extract_attendee_nested_response(payload, "bookingcode"), "booking-123")


class TestCalcomWebhookCallback(TestCase):
    @override_settings(DJ_CALCOM_QUERY_ACCESS_PARAM="test-secret")
    @patch("management.api.calcom.get_user_by_uuid")
    def test_meeting_ended_without_payload_does_not_raise(self, mock_get_user_by_uuid):
        webhook_body = {
            "triggerEvent": "MEETING_ENDED",
            "id": 123456,
            "title": "Meeting ended event without payload",
        }

        response = self.client.post(
            "/api/calcom/?secret=test-secret",
            data=json.dumps(webhook_body),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        mock_get_user_by_uuid.assert_not_called()

    @override_settings(DJ_CALCOM_QUERY_ACCESS_PARAM="test-secret")
    @patch("management.api.calcom.get_user_by_uuid")
    def test_booking_created_without_payload_does_not_raise(self, mock_get_user_by_uuid):
        webhook_body = {
            "triggerEvent": "BOOKING_CREATED",
            "id": 123456,
            "title": "Booking created without payload",
        }

        response = self.client.post(
            "/api/calcom/?secret=test-secret",
            data=json.dumps(webhook_body),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        mock_get_user_by_uuid.assert_not_called()
