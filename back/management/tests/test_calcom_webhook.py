import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from management.api.calcom import (
    _extract_attendee_nested_response,
    _extract_query_param_from_url,
    _extract_user_field_value,
)
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.profile import Profile
from management.models.user import User


def _booking_payload(
    *,
    start_time="2026-09-03T15:00:00Z",
    end_time="2026-09-03T16:00:00Z",
    responses=None,
    user_fields=None,
    attendees=None,
):
    return {
        "startTime": start_time,
        "endTime": end_time,
        "responses": responses or {},
        "userFieldsResponses": user_fields or {},
        "attendees": attendees or [],
    }


class TestCalcomFieldExtraction(TestCase):
    def test_extracts_uuid_from_user_fields_responses(self):
        payload = {"userFieldsResponses": {"uuid": {"value": "user-uuid"}}}
        self.assertEqual(_extract_user_field_value(payload, "uuid"), "user-uuid")

    def test_extracts_uuid_from_responses(self):
        payload = {"responses": {"uuid": {"value": "user-uuid"}}}
        self.assertEqual(_extract_user_field_value(payload, "uuid"), "user-uuid")

    def test_extracts_raw_string_uuid_from_responses(self):
        payload = {"responses": {"uuid": "user-uuid"}}
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


@override_settings(DJ_CALCOM_QUERY_ACCESS_PARAM="test-secret")
class TestCalcomWebhookCallback(TestCase):
    def setUp(self):
        self.message_patch = patch("management.models.user.User.message")
        self.push_patch = patch("management.api.calcom.onboarding_call_reminder_push_notification")
        self.sms_patch = patch("management.api.calcom.send_sms_background")
        self.ws_patch = patch("chat.consumers.messages.PreMatchingAppointmentBooked")
        self.message_patch.start()
        self.push_patch.start()
        self.sms_patch.start()
        self.ws_patch.start()
        self.addCleanup(self.message_patch.stop)
        self.addCleanup(self.push_patch.stop)
        self.addCleanup(self.sms_patch.stop)
        self.addCleanup(self.ws_patch.stop)

    def _post(self, webhook_body):
        return self.client.post(
            "/api/calcom/?secret=test-secret",
            data=json.dumps(webhook_body),
            content_type="application/json",
        )

    def _create_user(self, email, user_type, first_name):
        user = User.objects.create_user(
            email=email,
            password="Test123!",
            first_name=first_name,
            last_name="Test",
        )
        user.profile.user_type = user_type
        user.profile.save()
        return user

    def test_meeting_ended_without_payload_does_not_raise(self):
        webhook_body = {
            "triggerEvent": "MEETING_ENDED",
            "id": 123456,
            "title": "Meeting ended event without payload",
        }

        response = self._post(webhook_body)

        self.assertEqual(response.status_code, 200)

    def test_booking_created_without_payload_does_not_raise(self):
        webhook_body = {
            "triggerEvent": "BOOKING_CREATED",
            "id": 123456,
            "title": "Booking created without payload",
        }

        response = self._post(webhook_body)

        self.assertEqual(response.status_code, 200)

    def test_creates_appointment_from_top_level_custom_fields(self):
        volunteer = self._create_user("volunteer@example.com", Profile.TypeChoices.VOLUNTEER, "Hilke")
        payload = _booking_payload(
            responses={
                "email": {"value": "volunteer@example.com"},
                "uuid": {"value": str(volunteer.uuid)},
                "bookingcode": {"value": str(volunteer.state.prematch_booking_code)},
            },
            attendees=[{"email": "volunteer@example.com", "name": "Hilke"}],
        )

        response = self._post({"triggerEvent": "BOOKING_CREATED", "payload": payload})

        self.assertEqual(response.status_code, 200)
        appointment = PreMatchingAppointment.objects.get(user=volunteer)
        self.assertEqual(appointment.start_time.isoformat(), "2026-09-03T15:00:00+00:00")

    def test_learner_additional_seat_is_not_dropped_on_first_attendee_booking_code(self):
        volunteer = self._create_user("hilke.amer@yahoo.com", Profile.TypeChoices.VOLUNTEER, "Hilke")
        learner = self._create_user("dhirendra.iitb@gmail.com", Profile.TypeChoices.LEARNER, "Dhirendra")
        payload = _booking_payload(
            responses={
                "email": {"value": "Dhirendra.iitb@gmail.com"},
                "uuid": {"value": str(volunteer.uuid)},
                "bookingcode": {"value": str(volunteer.state.prematch_booking_code)},
            },
            user_fields={
                "uuid": {"value": str(volunteer.uuid)},
                "bookingcode": {"value": str(volunteer.state.prematch_booking_code)},
            },
            attendees=[
                {
                    "email": "hilke.amer@yahoo.com",
                    "name": "Hilke",
                    "bookingSeat": {
                        "data": {
                            "responses": {
                                "email": "hilke.amer@yahoo.com",
                                "uuid": str(volunteer.uuid),
                                "bookingcode": str(volunteer.state.prematch_booking_code),
                            }
                        }
                    },
                },
                {
                    "email": "Dhirendra.iitb@gmail.com",
                    "name": "Dhirendra",
                    "bookingSeat": {
                        "data": {
                            "responses": {
                                "email": "Dhirendra.iitb@gmail.com",
                            }
                        }
                    },
                },
            ],
        )

        response = self._post({"triggerEvent": "BOOKING_CREATED", "payload": payload})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(PreMatchingAppointment.objects.filter(user=learner).exists())
        self.assertTrue(PreMatchingAppointment.objects.filter(user=volunteer).exists())

    def test_mixed_case_email_creates_appointment_without_custom_fields(self):
        learner = self._create_user("ouyangzhennie@gmail.com", Profile.TypeChoices.LEARNER, "Zhennie")
        payload = _booking_payload(
            responses={"email": {"value": "OuyangZhennie@gmail.com"}},
            attendees=[{"email": "OuyangZhennie@gmail.com", "name": "Zhennie"}],
        )

        response = self._post({"triggerEvent": "BOOKING_CREATED", "payload": payload})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(PreMatchingAppointment.objects.filter(user=learner).exists())

    def test_all_learner_slot_is_created_from_attendee_email(self):
        learner = self._create_user("fataliyevamin@gmail.com", Profile.TypeChoices.LEARNER, "Amin")
        payload = _booking_payload(
            start_time="2026-09-02T17:00:00Z",
            end_time="2026-09-02T18:00:00Z",
            responses={"email": {"value": "fataliyevamin@gmail.com"}},
            attendees=[{"email": "fataliyevamin@gmail.com", "name": "Amin"}],
        )

        response = self._post({"triggerEvent": "BOOKING_CREATED", "payload": payload})

        self.assertEqual(response.status_code, 200)
        appointment = PreMatchingAppointment.objects.get(user=learner)
        self.assertEqual(appointment.start_time.hour, 17)
