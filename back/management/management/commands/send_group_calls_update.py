import urllib.parse

from django.conf import settings
from django.core.management.base import BaseCommand
from translations import get_translation

from management.controller import get_user_by_uuid


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument("arg1", type=str, help="User uuid")

    def handle(self, **options):
        user_uuid = options["arg1"]
        user = get_user_by_uuid(user_uuid)

        first_name = user.first_name

        message = get_translation("auto_messages.group_calls_announcement", lang="de").format(
            first_name=first_name,
            encoded_params=urllib.parse.urlencode(
                {"email": str(user.email), "uuid": str(user.uuid), "bookingcode": str(user.state.prematch_booking_code)}
            ),
            calcom_meeting_id=settings.DJ_CALCOM_MEETING_ID,
        )

        print("Sending message to", user, message)

        user.message(message, auto_mark_read=True, send_message_incoming=True)
