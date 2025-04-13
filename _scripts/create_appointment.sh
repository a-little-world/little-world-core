#!/bin/bash

# Default values
SECRET=${SECRET:-"secret"}
TRIGGER_EVENT=${TRIGGER_EVENT:-"BOOKING_CREATED"}
START_TIME=${START_TIME:-$(date -u +"%Y-%m-%dT%H:%M:%SZ")}
END_TIME=${END_TIME:-$(date -u -d "+15 minutes" +"%Y-%m-%dT%H:%M:%SZ")}
USER_HASH=${USER_HASH:-"bc3c8cf4-2004-47a1-95b9-7777e2979637-83e60138-0ef1-4ee4-81b4-4dd7e0d39b39"} #herrduenschnlate+13@gmail.com
BOOKING_CODE=${BOOKING_CODE:-"f1a879d2-d7b0-458c-898f-00094656bf22"} #herrduenschnlate+13@gmail.com
ORGANIZER_NAME=${ORGANIZER_NAME:-"Test Organizer"}
ORGANIZER_EMAIL=${ORGANIZER_EMAIL:-"tim.timschupp+420@gmail.com"}
ATTENDEE_NAME=${ATTENDEE_NAME:-"Test Attendee"}
ATTENDEE_EMAIL=${ATTENDEE_EMAIL:-"herrduenschnlate+13@gmail.com"}
MEETING_TITLE=${MEETING_TITLE:-"Test Meeting2"}
API_URL=${API_URL:-"http://localhost:8000/api/calcom/"}

# Create JSON payload
JSON_PAYLOAD=$(cat <<EOF
{
  "triggerEvent": "$TRIGGER_EVENT",
  "createdAt": "$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")",
  "payload": {
    "bookerUrl": "https://app.cal.com",
    "type": "15 Min Meeting",
    "title": "$MEETING_TITLE between $ORGANIZER_NAME and $ATTENDEE_NAME",
    "description": "",
    "additionalNotes": "",
    "customInputs": {},
    "startTime": "$START_TIME",
    "endTime": "$END_TIME",
    "organizer": {
      "id": 12345,
      "name": "$ORGANIZER_NAME",
      "email": "$ORGANIZER_EMAIL",
      "username": "test-username",
      "timeZone": "Europe/Berlin",
      "language": {"locale": "en"},
      "timeFormat": "h:mma"
    },
    "responses": {
      "name": {
        "label": "your_name",
        "value": "$ATTENDEE_NAME"
      },
      "email": {
        "label": "email_address",
        "value": "$ATTENDEE_EMAIL"
      },
      "location": {
        "label": "location",
        "value": {"optionValue": "", "value": "integrations:daily"}
      },
      "title": {
        "label": "what_is_this_meeting_about",
        "value": "$MEETING_TITLE"
      },
      "notes": {
        "label": "additional_notes"
      },
      "guests": {
        "label": "additional_guests",
        "value": []
      },
      "rescheduleReason": {"label": "reason_for_reschedule"},
      "hash": {"label": "Your user hash (do not change!)", "value": "$USER_HASH"}
    },
    "userFieldsResponses": {
      "hash": {"label": "Your user hash (do not change!)", "value": "$USER_HASH"},
      "bookingcode": {"label": "Booking Code", "value": "$BOOKING_CODE"}
    },
    "attendees": [
      {
        "email": "$ATTENDEE_EMAIL",
        "name": "$ATTENDEE_NAME",
        "firstName": "",
        "lastName": "",
        "timeZone": "Europe/Berlin",
        "language": {"locale": "en"}
      }
    ],
    "location": "integrations:daily",
    "videoCallData": {
      "type": "daily_video",
      "id": "test-meeting-id",
      "password": "test-password",
      "url": "https://meetco.daily.co/test-meeting-id"
    },
    "eventTitle": "15 Min Meeting",
    "eventDescription": "",
    "status": "ACCEPTED"
  }
}
EOF
)

# Make the POST request
echo "Sending request to $API_URL?secret=$SECRET"
curl -X POST "$API_URL?secret=$SECRET" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "X-Cal-Signature-256: dummy-signature" \
  -d "$JSON_PAYLOAD" \
  -v

echo -e "\n\nRequest completed."