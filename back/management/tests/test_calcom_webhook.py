import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from management.api.calcom import (
    _extract_attendee_nested_response,
    _extract_query_param_from_url,
    _extract_user_field_value,
    _triggering_identity,
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
    uid=None,
):
    payload = {
        "startTime": start_time,
        "endTime": end_time,
        "responses": responses or {},
        "userFieldsResponses": user_fields or {},
        "attendees": attendees or [],
    }
    if uid is not None:
        payload["uid"] = uid
    return payload


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

    def test_seated_event_does_not_inherit_top_level_uuid_and_bookingcode_for_new_seat(self):
        # Top-level email correctly tracks the new seat's booker, but uuid/bookingcode are
        # still the original booker's (the exact shape that hid learner bookings). With more
        # than one attendee, the new seat's own (missing) uuid/bookingcode must not be
        # backfilled from the top level.
        payload = {
            "responses": {
                "email": {"value": "new-seat@example.com"},
                "uuid": {"value": "original-booker-uuid"},
                "bookingcode": {"value": "original-booker-code"},
            },
            "attendees": [
                {
                    "email": "original-booker@example.com",
                    "bookingSeat": {
                        "data": {
                            "responses": {
                                "email": "original-booker@example.com",
                                "uuid": "original-booker-uuid",
                                "bookingcode": "original-booker-code",
                            }
                        }
                    },
                },
                {
                    "email": "new-seat@example.com",
                    "bookingSeat": {"data": {"responses": {"email": "new-seat@example.com"}}},
                },
            ],
        }

        identity, _ = _triggering_identity(payload)

        self.assertEqual(identity["email"], "new-seat@example.com")
        self.assertIsNone(identity["uuid"])
        self.assertIsNone(identity["bookingcode"])

    def test_single_attendee_booking_still_inherits_top_level_uuid_and_bookingcode(self):
        # A normal, non-seated booking has exactly one attendee and no bookingSeat data of its
        # own — the top-level custom fields are the only place uuid/bookingcode live.
        payload = {
            "responses": {
                "email": {"value": "solo@example.com"},
                "uuid": {"value": "solo-uuid"},
                "bookingcode": {"value": "solo-code"},
            },
            "attendees": [{"email": "solo@example.com"}],
        }

        identity, _ = _triggering_identity(payload)

        self.assertEqual(identity["email"], "solo@example.com")
        self.assertEqual(identity["uuid"], "solo-uuid")
        self.assertEqual(identity["bookingcode"], "solo-code")


@override_settings(DJ_CALCOM_QUERY_ACCESS_PARAM="test-secret")
class TestCalcomWebhookCallback(TestCase):
    def setUp(self):
        self.message_patch = patch("management.models.user.User.message")
        self.push_patch = patch("management.api.calcom.onboarding_call_reminder_push_notification")
        self.sms_patch = patch("management.api.calcom.send_sms_background")
        self.ws_patch = patch("chat.consumers.messages.PreMatchingAppointmentBooked")
        self.mock_message = self.message_patch.start()
        self.mock_push = self.push_patch.start()
        self.mock_sms = self.sms_patch.start()
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

    def test_later_seat_booking_does_not_reschedule_reminders_for_unchanged_attendee(self):
        # A group slot's second seat booking re-sends the first attendee too. Their own slot
        # hasn't moved, so their reminder tasks must not be rescheduled again.
        first = self._create_user("first@example.com", Profile.TypeChoices.VOLUNTEER, "First")
        second = self._create_user("second@example.com", Profile.TypeChoices.LEARNER, "Second")

        first_payload = _booking_payload(
            responses={"email": {"value": "first@example.com"}},
            attendees=[{"email": "first@example.com"}],
        )
        response = self._post({"triggerEvent": "BOOKING_CREATED", "payload": first_payload})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.mock_push.apply_async.call_count, 1)

        second_payload = _booking_payload(
            responses={"email": {"value": "second@example.com"}},
            attendees=[{"email": "first@example.com"}, {"email": "second@example.com"}],
        )
        response = self._post({"triggerEvent": "BOOKING_CREATED", "payload": second_payload})
        self.assertEqual(response.status_code, 200)

        # Only the new seat's reminder was scheduled; the first attendee's was left alone.
        self.assertEqual(self.mock_push.apply_async.call_count, 2)
        scheduled_user_pks = {call.args[0][0] for call in self.mock_push.apply_async.call_args_list}
        self.assertEqual(scheduled_user_pks, {first.pk, second.pk})
        self.assertTrue(PreMatchingAppointment.objects.filter(user=first).exists())
        self.assertTrue(PreMatchingAppointment.objects.filter(user=second).exists())

    def test_rebook_still_reschedules_reminder_for_same_user(self):
        # A genuine rebook (the same user, new time) must still reschedule reminders.
        user = self._create_user("rebooker@example.com", Profile.TypeChoices.LEARNER, "Rebooker")

        payload = _booking_payload(
            responses={"email": {"value": "rebooker@example.com"}},
            attendees=[{"email": "rebooker@example.com"}],
        )
        self._post({"triggerEvent": "BOOKING_CREATED", "payload": payload})
        self.assertEqual(self.mock_push.apply_async.call_count, 1)

        rebooked_payload = _booking_payload(
            start_time="2026-09-04T15:00:00Z",
            end_time="2026-09-04T16:00:00Z",
            responses={"email": {"value": "rebooker@example.com"}},
            attendees=[{"email": "rebooker@example.com"}],
        )
        self._post({"triggerEvent": "BOOKING_CREATED", "payload": rebooked_payload})

        self.assertEqual(self.mock_push.apply_async.call_count, 2)
        appointment = PreMatchingAppointment.objects.get(user=user)
        self.assertEqual(appointment.start_time.isoformat(), "2026-09-04T15:00:00+00:00")

    def test_notifies_resolved_attendee_when_triggering_identity_fails_to_resolve(self):
        # The merged/top-level identity can end up pointing at nobody (a stale uuid discarded
        # by the cross-check, an unmatched top-level email) while an attendee's own identity
        # still resolves cleanly. That attendee should still get the booked confirmation.
        real_user = self._create_user("realuser@example.com", Profile.TypeChoices.LEARNER, "Real")

        payload = {
            "startTime": "2026-09-03T15:00:00Z",
            "endTime": "2026-09-03T16:00:00Z",
            "responses": {
                "email": {"value": "ghost@example.com"},
                "bookingcode": {"value": "bogus-code"},
            },
            "attendees": [
                {"bookingSeat": {"data": {"responses": {"uuid": str(real_user.uuid)}}}},
            ],
        }

        response = self._post({"triggerEvent": "BOOKING_CREATED", "payload": payload})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(PreMatchingAppointment.objects.filter(user=real_user).exists())
        self.mock_message.assert_called_once()

    def test_booking_created_stores_calcom_uid(self):
        user = self._create_user("uid@example.com", Profile.TypeChoices.LEARNER, "Uid")
        payload = _booking_payload(
            responses={"email": {"value": "uid@example.com"}},
            attendees=[{"email": "uid@example.com"}],
            uid="booking-uid-1",
        )

        response = self._post({"triggerEvent": "BOOKING_CREATED", "payload": payload})

        self.assertEqual(response.status_code, 200)
        appointment = PreMatchingAppointment.objects.get(user=user)
        self.assertEqual(appointment.calcom_booking_uid, "booking-uid-1")

    def test_reschedule_updates_same_row_and_reschedules_reminders(self):
        user = self._create_user("resched@example.com", Profile.TypeChoices.LEARNER, "Resched")
        created_payload = _booking_payload(
            responses={"email": {"value": "resched@example.com"}},
            attendees=[{"email": "resched@example.com"}],
            uid="booking-uid-1",
        )
        self._post({"triggerEvent": "BOOKING_CREATED", "payload": created_payload})
        self.assertEqual(self.mock_push.apply_async.call_count, 1)
        appointment = PreMatchingAppointment.objects.get(user=user)
        original_uuid = appointment.uuid

        rescheduled_payload = _booking_payload(
            start_time="2026-09-04T15:00:00Z",
            end_time="2026-09-04T16:00:00Z",
            responses={"email": {"value": "resched@example.com"}},
            attendees=[{"email": "resched@example.com"}],
            uid="booking-uid-2",
        )
        rescheduled_payload["rescheduleUid"] = "booking-uid-1"

        response = self._post({"triggerEvent": "BOOKING_RESCHEDULED", "payload": rescheduled_payload})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PreMatchingAppointment.objects.filter(user=user).count(), 1)
        appointment.refresh_from_db()
        self.assertEqual(appointment.uuid, original_uuid)
        self.assertEqual(appointment.calcom_booking_uid, "booking-uid-2")
        self.assertEqual(appointment.start_time.isoformat(), "2026-09-04T15:00:00+00:00")
        self.assertEqual(self.mock_push.apply_async.call_count, 2)

    def test_booking_cancelled_deletes_row_and_cancels_sms(self):
        user = self._create_user("cancel@example.com", Profile.TypeChoices.LEARNER, "Cancel")
        payload = _booking_payload(
            responses={"email": {"value": "cancel@example.com"}},
            attendees=[{"email": "cancel@example.com"}],
            uid="cancel-uid",
        )
        self._post({"triggerEvent": "BOOKING_CREATED", "payload": payload})
        appointment = PreMatchingAppointment.objects.get(user=user)
        appointment.sms_task = "sms-task-id"
        appointment.save(update_fields=["sms_task"])

        with patch("management.api.calcom.end_task") as mock_end_task:
            response = self._post({"triggerEvent": "BOOKING_CANCELLED", "payload": payload})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(PreMatchingAppointment.objects.filter(user=user).exists())
        mock_end_task.assert_called_once_with(task_id="sms-task-id")

    def test_cancellation_for_superseded_uid_does_not_delete_newer_booking(self):
        user = self._create_user("superseded@example.com", Profile.TypeChoices.LEARNER, "Superseded")
        payload = _booking_payload(
            responses={"email": {"value": "superseded@example.com"}},
            attendees=[{"email": "superseded@example.com"}],
            uid="new-uid",
        )
        self._post({"triggerEvent": "BOOKING_CREATED", "payload": payload})

        stale_cancel = _booking_payload(
            responses={"email": {"value": "superseded@example.com"}},
            attendees=[{"email": "superseded@example.com"}],
            uid="old-uid",
        )
        response = self._post({"triggerEvent": "BOOKING_CANCELLED", "payload": stale_cancel})

        self.assertEqual(response.status_code, 200)
        appointment = PreMatchingAppointment.objects.get(user=user)
        self.assertEqual(appointment.calcom_booking_uid, "new-uid")

    def test_new_booking_deletes_stale_duplicate_rows(self):
        user = self._create_user("dup@example.com", Profile.TypeChoices.LEARNER, "Dup")
        start = timezone.now()
        PreMatchingAppointment.objects.create(user=user, start_time=start, end_time=start)
        PreMatchingAppointment.objects.create(user=user, start_time=start, end_time=start)

        payload = _booking_payload(
            responses={"email": {"value": "dup@example.com"}},
            attendees=[{"email": "dup@example.com"}],
            uid="new-uid",
        )
        response = self._post({"triggerEvent": "BOOKING_CREATED", "payload": payload})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PreMatchingAppointment.objects.filter(user=user).count(), 1)
        appointment = PreMatchingAppointment.objects.get(user=user)
        self.assertEqual(appointment.calcom_booking_uid, "new-uid")


class TestAdminCreateAppointmentInvalidatesPrior(TestCase):
    def test_create_appointment_for_user_deletes_prior_rows(self):
        from rest_framework.test import APIClient

        user = User.objects.create_user(
            email="admin-appt@example.com",
            password="Test123!",
            first_name="Appt",
            last_name="User",
        )
        start = timezone.now()
        stale = PreMatchingAppointment.objects.create(user=user, start_time=start, end_time=start)

        staff = User.objects.create_user(
            email="staff@example.com",
            password="Test123!",
            first_name="Staff",
            last_name="User",
        )
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        client = APIClient()
        client.force_authenticate(user=staff)

        response = client.post(
            "/api/matching/prematchingappointments/create_appointment_for_user/",
            data={"user_id": user.id, "start_time": "2026-09-05T10:00:00Z"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(PreMatchingAppointment.objects.filter(user=user).count(), 1)
        self.assertFalse(PreMatchingAppointment.objects.filter(pk=stale.pk).exists())


class TestUserDataAppointmentLink(TestCase):
    def test_returns_reschedule_link_once_uid_stored(self):
        from management.api.user import get_user_data

        user = User.objects.create_user(
            email="link@example.com",
            password="Test123!",
            first_name="Link",
            last_name="User",
        )
        start = timezone.now()
        PreMatchingAppointment.objects.create(
            user=user,
            start_time=start,
            end_time=start,
            calcom_booking_uid="uid-abc",
        )

        data = get_user_data(user)

        self.assertIn("rescheduleUid=uid-abc", data["calComAppointmentLink"])

    def test_returns_prefill_link_without_uid(self):
        from management.api.user import get_user_data

        user = User.objects.create_user(
            email="nolink@example.com",
            password="Test123!",
            first_name="No",
            last_name="Link",
        )
        start = timezone.now()
        PreMatchingAppointment.objects.create(user=user, start_time=start, end_time=start)

        data = get_user_data(user)

        self.assertNotIn("rescheduleUid", data["calComAppointmentLink"])
        self.assertIn("bookingcode=", data["calComAppointmentLink"])
