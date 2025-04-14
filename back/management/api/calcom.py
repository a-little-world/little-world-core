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
            'username': 'tim-schupp-o8evyj',
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
        'hash': {'label': 'Your user hash ( no not change! )', 'value': 'c73032ba-ed7a-438b-84b9-fbe9d5ce4aa6-56cec83d-7bba-4dbd-8987-b1a7eff74ea4'}}, 'userFieldsResponses': {'hash': {'label': 'Your user hash ( no not change! )', 'value': 'c73032ba-ed7a-438b-84b9-fbe9d5ce4aa6-56cec83d-7bba-4dbd-8987-b1a7eff74ea4'}}, 'attendees': [{'email': 'herrduenschnlate+77@gmail.com', 'name': 'Tim Schupp', 'firstName': '', 'lastName': '', 'timeZone': 'Europe/Berlin', 'language': {'locale': 'en'}}], 'location': 'integrations:daily', 'destinationCalendar': [{'id': 130667, 'integration': 'google_calendar', 'externalId': 'tim.timschupp@gmail.com', 'userId': 127722, 'eventTypeId': None, 'credentialId': 191664}], 'hideCalendarNotes': False, 'requiresConfirmation': None, 'eventTypeId': 437906, 'seatsShowAttendees': True, 'seatsPerTimeSlot': None, 'seatsShowAvailabilityCount': True, 'schedulingType': None, 'uid': 'iJRcxoRXJZRNFHt1k4qsAL', 'conferenceData': {'createRequest': {'requestId': '2db644eb-37a5-581a-99fa-ebe6ce513834'}}, 'videoCallData': {'type': 'daily_video', 'id': 'bHYP69oSSGXhDLlbX5ne', 'password': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyIjoiYkhZUDY5b1NTR1hoRExsYlg1bmUiLCJleHAiOjE2OTcxMDU3MDAsIm8iOnRydWUsImQiOiJiYmQ5OGE3MS0xOWM5LTRiYjEtYTVjNS1jYWYxZWM1YmQxMDUiLCJpYXQiOjE2OTY5NTY1OTB9.o3jx_WBK6lpJZR3ugxFiy0_-Lhr5ZPDn2MYfbj4ao08', 'url': 'https://meetco.daily.co/bHYP69oSSGXhDLlbX5ne'}, 'iCalUID': 'f6s1ah90v85jp0h1q5i9gd2hqk@google.com', 'appsStatus': [{'appName': 'daily-video', 'type': 'daily_video', 'success': 1, 'failures': 0, 'errors': []}, {'appName': 'google-calendar', 'type': 'google_calendar', 'success': 1, 'failures': 0, 'errors': [], 'warnings': []}], 'eventTitle': '15 Min Meeting', 'eventDescription': '', 'price': 0, 'currency': 'usd', 'length': 15, 'bookingId': 781718, 'metadata': {'videoCallUrl': 'https://app.cal.com/video/iJRcxoRXJZRNFHt1k4qsAL'}, 'status': 'ACCEPTED'}}

{'REQUEST_METHOD': 'POST', 'QUERY_STRING': '', 'SCRIPT_NAME': '', 'PATH_INFO': '/api/calcom/', 'wsgi.multithread': True, 'wsgi.multiprocess': True, 'REMOTE_ADDR': '172.18.0.1', 'REMOTE_HOST': '172.18.0.1', 'REMOTE_PORT': 43876, 'SERVER_NAME': '172.18.0.2', 'SERVER_PORT': '8000', 'HTTP_HOST': '6fac
-212-91-248-146.ngrok-free.app', 'HTTP_USER_AGENT': 'undici', 'CONTENT_LENGTH': '2931', 'HTTP_ACCEPT': '*/*', 'HTTP_ACCEPT_ENCODING': 'br, gzip, deflate', 'HTTP_ACCEPT_LANGUAGE': '*', 'CONTENT_TYPE': 'application/json', 'HTTP_SEC_FETCH_MODE': 'cors', 'HTTP_X_CAL_SIGNATURE_256': '7705e2a78e21089611cb48c8b1aae6bbfd61c3b99465c275ecc7ab
bd34b6821b', 'HTTP_X_FORWARDED_FOR': '3.238.174.157', 'HTTP_X_FORWARDED_PROTO': 'https', 'HTTP_X_VERCEL_ID': 'fra1::67l8j-1697028209487-020e577bdc4d'}
"""

import pytz
from management.controller import get_base_management_user
from babel.dates import format_datetime
from dateutil import parser
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from back.celery import end_task
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from translations import get_translation

from management.controller import get_user_by_hash
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer

from management.tasks import send_sms_background
from datetime import datetime, timedelta


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


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def callcom_websocket_callback(request):
    """
    Received callcom event callbacks, this should simply send a message in the admin chat if an appointment was booked.
    """

    assert request.query_params["secret"] == settings.DJ_CALCOM_QUERY_ACCESS_PARAM

    event_type = request.data["triggerEvent"]
    start_time_normalized = translate_to_german_date(request.data["payload"]["startTime"])
    # end_time = translate_to_german_date(request.data["payload"]["endTime"])
    # organizer_email = request.data["payload"]["organizer"]["email"]
    user_hash = request.data["payload"]["userFieldsResponses"]["hash"]["value"]
    booking_code = request.data["payload"]["userFieldsResponses"]["bookingcode"]["value"]

    user = get_user_by_hash(user_hash)

    print("EVENT TYPE", event_type, user, booking_code, start_time_normalized, request.data["payload"]["startTime"])
    print(request.data)

    if event_type == "BOOKING_CREATED":
        assert str(user.state.prematch_booking_code) == str(booking_code)

        user.message(
            get_translation("auto_messages.appointment_booked", lang="de").format(
                appointment_time=start_time_normalized
            ),
            auto_mark_read=True,
            send_message_incoming=True,
        )

        appointment = PreMatchingAppointment.objects.filter(user=user)
        start_time_parsed = parse_datetime(request.data["payload"]["startTime"])
        end_time_parsed = parse_datetime(request.data["payload"]["endTime"])
        if appointment.exists():
            appointment = appointment.first()
            appointment.end_time = end_time_parsed
            appointment.start_time = start_time_parsed
            end_task(task_id=appointment.sms_task)
            new_async_result = send_sms_background.apply_async(
                (user_hash, get_translation("sms.onboarding_in_30min", lang="de")),
                eta=start_time_parsed - timedelta(minutes=30)
            )
            appointment.sms_task = new_async_result.id
            appointment.save()
        else:
            appointment = PreMatchingAppointment(user=user, start_time=start_time_parsed, end_time=end_time_parsed)
            async_result = send_sms_background.apply_async(
                (user_hash, get_translation("sms.onboarding_in_30min", lang="de")),
                eta=start_time_parsed - timedelta(minutes=30)
            )
            appointment.sms_task = async_result.id
            appointment.save()
            
        from chat.consumers.messages import PreMatchingAppointmentBooked
        PreMatchingAppointmentBooked(appointment=PreMatchingAppointmentSerializer(appointment).data).send(user.hash)

        # Comment Oliver: we don't need to send this you already see it in the app & you get an email.
        # user.sms(get_base_management_user(), get_translation("sms.appointment_booked", lang="de").format(appointment_time=start_time_normalized))

    return Response("ok")
