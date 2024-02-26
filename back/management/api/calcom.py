"""
This contains all api's related to confirming or denying a match


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
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from typing import Literal
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.views.i18n import JavaScriptCatalog, JSONCatalog
from django.utils.translation.trans_real import DjangoTranslation
from django.utils.translation import get_language
from django.conf import settings
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from dataclasses import dataclass
from django.utils.translation import pgettext_lazy
from rest_framework import serializers
from babel.dates import format_date, format_datetime, format_time
from datetime import datetime
from django.utils import timezone

def translate_to_german_date(date_str):
    date_format = "%Y-%m-%dT%H:%M:%SZ"
    date_object = datetime.strptime(date_str, date_format)

    local_datetime = timezone.localtime(date_object)
    german_date_string = format_datetime(local_datetime, 'full', locale='de_DE')
    
    return german_date_string


@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def callcom_websocket_callback(request):
    """
    Received callcom event callbacks, this should simply send a message in the admin chat if an appointment was booked.
    """
    
    from management.controller import get_user_by_hash, send_websocket_callback
    assert request.query_params["secret"] == settings.DJ_CALCOM_QUERY_ACCESS_PARAM
    
    event_type = request.data["triggerEvent"]
    start_time = translate_to_german_date(request.data["payload"]["startTime"])
    end_time = translate_to_german_date(request.data["payload"]["endTime"])
    organizer_email = request.data["payload"]["organizer"]["email"]
    user_hash = request.data["payload"]["userFieldsResponses"]["hash"]["value"]
    booking_code = request.data["payload"]["userFieldsResponses"]["bookingcode"]["value"]
    
    user = get_user_by_hash(user_hash)
    
    if event_type == "BOOKING_CREATED":
        assert str(user.state.prematch_booking_code) == str(booking_code)
        # TODO: correctly insert the support user name
        
        from django.utils import timezone
        
        user.message(
           f"Der Termin für dein Einführungsgespräch wurde gebucht von <b>{start_time}</b> bis <b>{end_time}</b> mit Tim Schupp.\nFalls du den Termin absagen oder umbuchen möchtest, sage den termin ab und buche einen neuen, oder schreibe mir bitte eine kurze Nachricht." 
        )
        
        
        appointment = PreMatchingAppointment.objects.filter(user=user)
        from management.api.slack import notify_communication_channel

        start_time_parsed = parse_datetime(request.data["payload"]["startTime"])
        end_time_parsed = parse_datetime(request.data["payload"]["endTime"])
        if appointment.exists():
            
            appointment = appointment.first()

            #'startTime': '2023-10-12T09:00:00Z', 
            #'endTime': '2023-10-12T09:15:00Z', 
            # we need to parse the date string and convert it to a datetime object
            previous_start_time = format_datetime(appointment.start_time, 'full', locale='de_DE')
            appointment.end_time = end_time_parsed
            appointment.start_time = start_time_parsed
            appointment.save()
            
            notify_communication_channel(
               f"\Appointment Updated {previous_start_time} -> {start_time}\nCall link: https://little-world.com/app/call-setup/{user.hash}/" 
            )
        else:
            appointment = PreMatchingAppointment(
                user=user,
                start_time=start_time_parsed,
                end_time=end_time_parsed
            )
            appointment.save()
            notify_communication_channel(
               f"A new appointment was booked by a user.\nWhen: {start_time}\nCall link: https://little-world.com/app/call-setup/{user.hash}/" 
            )
        
        from chat.consumers.messages import PreMatchingAppointmentBooked
        
        PreMatchingAppointmentBooked(
            appointment=PreMatchingAppointmentSerializer(appointment).data
        ).send(user.hash)
        
        

    
    return Response("ok")