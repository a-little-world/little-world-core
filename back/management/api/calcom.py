"""
{
    'triggerEvent': 'BOOKING_CREATED',
    'createdAt': '2023-10-10T16:49:50.991Z',
    'payload': {
        'bookerUrl': 'https://app.cal.com',
        'type': '15 Min Meeting',
        'title': '15 Min Meeting between Tim Schupp and Tim Schupp',
        'description': '',
        'additionalNotes': '',
        'customInputs': {},
        'startTime': '2023-10-12T09:00:00Z',
        'endTime': '2023-10-12T09:15:00Z',
        'organizer': {
            'id': 127722,
            'name': 'Tim Schupp',
            'email': 'tim.timschupp@gmail.com',
            'username': 'SOMENAME',
            'timeZone': 'Europe/Berlin',
            'language': {'locale': 'en'},
            'timeFormat': 'h:mma'
        },
        'responses': {
            'name': {
                'label': 'your_name',
                'value': 'Tim Schupp'
            },
            'email': {
                'label': 'email_address',
                'value': 'herrduenschnlate+77@gmail.com'
            },
        'location': {
            'label': 'location',
            'value': {'optionValue': '',
            'value': 'integrations:daily'}},
        'title': {
            'label': 'what_is_this_meeting_about',
            'value': 'Test'
        },
        'notes': {
            'label': 'additional_notes'
        },
        'guests': {
            'label': 'additional_guests',
            'value': []
        },
        'rescheduleReason': {'label': 'reason_for_reschedule'},
        'hash': {'label': 'Your user hash ( no not change! )', 'value': 'c73032ba-ed7a-438b-84b9-fbe9d5ce4aa6-56cec83d-7bba-4dbd-8987-b1a7eff74ea4'}}, 'userFieldsResponses': {'hash': {'label': 'Your user hash ( no not change! )', 'value': 'c73032ba-ed7a-438b-84b9-fbe9d5ce4aa6-56cec83d-7bba-4dbd-8987-b1a7eff74ea4'}}, 'attendees': [{'email': 'example@user.com', 'name': 'Tim Schupp', 'firstName': '', 'lastName': '', 'timeZone': 'Europe/Berlin', 'language': {'locale': 'en'}}], 'location': 'integrations:daily', 'destinationCalendar': [{'id': 130667, 'integration': 'google_calendar', 'externalId': 'tim.timschupp@gmail.com', 'userId': 127722, 'eventTypeId': None, 'credentialId': 191664}], 'hideCalendarNotes': False, 'requiresConfirmation': None, 'eventTypeId': 437906, 'seatsShowAttendees': True, 'seatsPerTimeSlot': None, 'seatsShowAvailabilityCount': True, 'schedulingType': None, 'uid': 'iJRcxoRXJZRNFHt1k4qsAL', 'conferenceData': {'createRequest': {'requestId': '2db644eb-37a5-581a-99fa-ebe6ce513834'}}, 'videoCallData': {'type': 'daily_video', 'id': 'bHYP69oSSGXhDLlbX5ne', 'password': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyIjoiYkhZUDY5b1NTR1hoRExsYlg1bmUiLCJleHAiOjE2OTcxMDU3MDAsIm8iOnRydWUsImQiOiJiYmQ5OGE3MS0xOWM5LTRiYjEtYTVjNS1jYWYxZWM1YmQxMDUiLCJpYXQiOjE2OTY5NTY1OTB9.o3jx_WBK6lpJZR3ugxFiy0_-Lhr5ZPDn2MYfbj4ao08', 'url': 'https://meetco.daily.co/bHYP69oSSGXhDLlbX5ne'}, 'iCalUID': 'f6s1ah90v85jp0h1q5i9gd2hqk@google.com', 'appsStatus': [{'appName': 'daily-video', 'type': 'daily_video', 'success': 1, 'failures': 0, 'errors': []}, {'appName': 'google-calendar', 'type': 'google_calendar', 'success': 1, 'failures': 0, 'errors': [], 'warnings': []}], 'eventTitle': '15 Min Meeting', 'eventDescription': '', 'price': 0, 'currency': 'usd', 'length': 15, 'bookingId': 781718, 'metadata': {'videoCallUrl': 'LITTLE WORLD LINK!'}, 'status': 'ACCEPTED'}}

{'REQUEST_METHOD': 'POST', 'QUERY_STRING': '', 'SCRIPT_NAME': '', 'PATH_INFO': '/api/calcom/', 'wsgi.multithread': True, 'wsgi.multiprocess': True, 'REMOTE_ADDR': 'ADDR', 'REMOTE_HOST': 'REMOE', 'REMOTE_PORT': 43876, 'SERVER_NAME': 'NAME', 'SERVER_PORT': '8000', 'HTTP_HOST': 'HOSTNAME', 'HTTP_USER_AGENT': 'USER_AGENT', 'CONTENT_LENGTH': '2931', 'HTTP_ACCEPT': '*/*', 'HTTP_ACCEPT_ENCODING': 'br, gzip, deflate', 'HTTP_ACCEPT_LANGUAGE': '*', 'CONTENT_TYPE': 'application/json', 'HTTP_SEC_FETCH_MODE': 'cors', 'HTTP_X_CAL_SIGNATURE_256': '7705e2a78e21089611cb48c8b1aae6bbfd61c3b99465c275ecc7ab
bd34b6821b', 'HTTP_X_FORWARDED_FOR': 'X_FORWARDED_FOR', 'HTTP_X_FORWARDED_PROTO': 'https', 'HTTP_X_VERCEL_ID': 'VERCEL_ID'}
"""

import urllib.parse
from datetime import timedelta

import pytz
from babel.dates import format_datetime
from back.celery import end_task
from dateutil import parser
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from translations import get_translation

from management.controller import UserNotFoundErr, get_user_by_email, get_user_by_uuid
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
from management.models.state import State
from management.tasks import send_sms_background


def translate_to_german_date(date_str, target_timezone="Europe/Berlin"):
    date_object = parser.parse(date_str)

    # Ensure the datetime is timezone-aware, set to the source timezone if it's naive
    if timezone.is_naive(date_object):
        date_object = timezone.make_aware(date_object, timezone.utc)

    target_tz = pytz.timezone(target_timezone)
    localized_date_object = date_object.astimezone(target_tz)

    german_date_string = format_datetime(
        localized_date_object, "EEEE, d. MMMM yyyy, 'um' HH:mm 'Uhr (deutsche Zeit)'", locale="de_DE"
    )

    return german_date_string


def _extract_user_field_value(payload, field_name):
    user_fields_responses = payload.get("userFieldsResponses", {}) or {}
    if isinstance(user_fields_responses, dict):
        value = user_fields_responses.get(field_name, {}).get("value")
        if value:
            return value

    responses = payload.get("responses", {}) or {}
    if isinstance(responses, dict):
        value = responses.get(field_name, {}).get("value")
        if value:
            return value

    custom_inputs = payload.get("customInputs", {}) or {}
    if isinstance(custom_inputs, dict):
        value = custom_inputs.get(field_name)
        if value:
            return value

    metadata = payload.get("metadata", {}) or {}
    if isinstance(metadata, dict):
        value = metadata.get(field_name)
        if value:
            return value

    value = payload.get(field_name)
    if value:
        return value

    return None


def _extract_query_param_from_url(url, field_name):
    if not url or not isinstance(url, str):
        return None
    parsed = urllib.parse.urlparse(url)
    values = urllib.parse.parse_qs(parsed.query).get(field_name, [])
    return values[0] if values else None


def _extract_attendee_nested_response(payload, field_name):
    attendees = payload.get("attendees", []) or []
    if not isinstance(attendees, list):
        return None
    for attendee in attendees:
        if not isinstance(attendee, dict):
            continue
        booking_seat = attendee.get("bookingSeat", {}) or {}
        if not isinstance(booking_seat, dict):
            continue
        data = booking_seat.get("data", {}) or {}
        if not isinstance(data, dict):
            continue
        responses = data.get("responses", {}) or {}
        if not isinstance(responses, dict):
            continue
        value = responses.get(field_name)
        if value:
            return value
    return None


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def callcom_websocket_callback(request):
    """
    Received callcom event callbacks, this should simply send a message in the admin chat if an appointment was booked.
    """

    assert request.query_params["secret"] == settings.DJ_CALCOM_QUERY_ACCESS_PARAM

    event_type = request.data.get("triggerEvent")
    if event_type != "BOOKING_CREATED":
        return Response("ok")

    payload = request.data.get("payload")
    if not isinstance(payload, dict):
        return Response("ok")

    start_time = payload.get("startTime")
    end_time = payload.get("endTime")
    user_uuid = _extract_user_field_value(payload, "uuid")
    if not user_uuid:
        # Legacy fallback for old booking forms.
        user_uuid = _extract_user_field_value(payload, "hash")
    booking_code = _extract_user_field_value(payload, "bookingcode")
    if not user_uuid:
        for url_field_name in ("bookerUrl", "bookingUrl", "rescheduleUrl", "cancelUrl"):
            url_value = payload.get(url_field_name)
            user_uuid = _extract_query_param_from_url(url_value, "uuid") or _extract_query_param_from_url(
                url_value, "hash"
            )
            if user_uuid:
                break

    if not booking_code:
        for url_field_name in ("bookerUrl", "bookingUrl", "rescheduleUrl", "cancelUrl"):
            url_value = payload.get(url_field_name)
            booking_code = _extract_query_param_from_url(url_value, "bookingcode")
            if booking_code:
                break
    if not booking_code:
        booking_code = _extract_attendee_nested_response(payload, "bookingcode")

    user_email = _extract_user_field_value(payload, "email")
    if not user_email:
        attendees = payload.get("attendees", []) or []
        if isinstance(attendees, list) and len(attendees) > 0 and isinstance(attendees[0], dict):
            user_email = attendees[0].get("email")

    if not start_time or not end_time or (not user_uuid and not user_email):
        print(
            "CALCOM: missing required fields",
            {
                "start_time": bool(start_time),
                "end_time": bool(end_time),
                "user_uuid": bool(user_uuid),
                "user_email": bool(user_email),
            },
        )
        return Response("ok")

    start_time_normalized = translate_to_german_date(start_time)
    # end_time = translate_to_german_date(payload["endTime"])
    # organizer_email = payload["organizer"]["email"]

    user = None
    if user_uuid:
        try:
            user = get_user_by_uuid(user_uuid)
        except (ValueError, LookupError, UserNotFoundErr):
            user = None
    if user is None and user_email:
        try:
            user = get_user_by_email(user_email)
        except UserNotFoundErr:
            user = None
    if user is None and booking_code:
        user_state = State.objects.select_related("user").filter(prematch_booking_code=str(booking_code)).first()
        if user_state is not None:
            user = user_state.user
    if user is None:
        print(
            "CALCOM: unable to resolve user",
            {"user_uuid": user_uuid, "user_email": user_email, "booking_code": booking_code},
        )
        return Response("ok")

    print("CALCOM: booking created", {"user": str(user.uuid), "booking_code": booking_code, "start_time": start_time})

    if event_type == "BOOKING_CREATED":
        expected_booking_code = str(user.state.prematch_booking_code)
        if booking_code and str(booking_code) != expected_booking_code:
            print(
                "CALCOM: booking code mismatch",
                {"user_uuid": str(user.uuid), "expected": expected_booking_code, "received": str(booking_code)},
            )
            return Response("ok")
        if not booking_code:
            print("CALCOM: booking code missing, proceeding with uuid", {"user_uuid": str(user.uuid)})

        user.message(
            get_translation("auto_messages.appointment_booked", lang="de").format(
                appointment_time=start_time_normalized
            ),
            auto_mark_read=True,
            send_message_incoming=True,
        )

        appointment = PreMatchingAppointment.objects.filter(user=user)
        start_time_parsed = parse_datetime(start_time)
        end_time_parsed = parse_datetime(end_time)
        if not start_time_parsed or not end_time_parsed:
            return Response("ok")
        if appointment.exists():
            appointment = appointment.first()
            appointment.end_time = end_time_parsed
            appointment.start_time = start_time_parsed
            end_task(task_id=appointment.sms_task)

            # First check if that user should even receive SMS! Otherwise this flods the queue with shduled tasks that in the end don't do anything!
            if user.profile.notify_channel == "sms" and user.profile.phone_mobile != "":
                new_async_result = send_sms_background.apply_async(
                    (user_uuid, get_translation("sms.onboarding_in_1h", lang="de").format(first_name=user.first_name)),
                    eta=start_time_parsed - timedelta(hours=1),
                )
                appointment.sms_task = new_async_result.id
            appointment.save()
        else:
            appointment = PreMatchingAppointment(user=user, start_time=start_time_parsed, end_time=end_time_parsed)
            if user.profile.notify_channel == "sms" and user.profile.phone_mobile != "":
                async_result = send_sms_background.apply_async(
                    (user_uuid, get_translation("sms.onboarding_in_1h", lang="de").format(first_name=user.first_name)),
                    eta=start_time_parsed - timedelta(hours=1),
                )
                appointment.sms_task = async_result.id
            appointment.save()

        from chat.consumers.messages import PreMatchingAppointmentBooked

        PreMatchingAppointmentBooked(appointment=PreMatchingAppointmentSerializer(appointment).data).send(
            str(user.uuid)
        )

        # Comment Oliver: we don't need to send this you already see it in the app & you get an email.
        # user.sms(get_base_management_user(), get_translation("sms.appointment_booked", lang="de").format(appointment_time=start_time_normalized))

    return Response("ok")
