from django.core.management.base import BaseCommand

from management.meta_capi import MetaCAPIClient, build_event, build_user_data


class Command(BaseCommand):
    help = "Send a Meta CAPI test event."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=False)
        parser.add_argument("--event-name", default="Lead")

    def handle(self, *args, **options):
        email = options.get("email")
        event_name = options["event_name"]

        user_data = build_user_data(
            email=email,
            client_ip_address="127.0.0.1",
            client_user_agent="Django Meta CAPI Smoke Test",
        )

        event = build_event(
            event_name=event_name,
            event_id="test_event:manual",
            user_data=user_data,
            event_source_url="https://example.com/meta-capi-test",
            custom_data={
                "content_name": "Manual Test Event",
            },
        )

        response = MetaCAPIClient().send_events([event])
        self.stdout.write(self.style.SUCCESS(str(response)))
