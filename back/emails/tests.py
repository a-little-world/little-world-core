from datetime import datetime

from django.test import TestCase
from management.controller import create_user_matching_proposal, match_users
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.tests.helpers import register_user

from emails.api.emails_config import EMAILS_CONFIG
from emails.api.render_template import get_full_template_info, render_template_dynamic_lookup


class EmailTests(TestCase):
    def test_send_all_emails(self):
        # Test sending all emails
        u1 = register_user()
        u2 = register_user()
        u3 = register_user()

        start_date = datetime(2024, 10, 9, 23, 55, 59, 342380)
        PreMatchingAppointment.objects.create(user=u1, start_time=start_date, end_time=start_date)

        match = match_users({u1, u2})
        proposal = create_user_matching_proposal({u1, u3}, send_confirm_match_email=False)

        for template_name in EMAILS_CONFIG.emails:
            if template_name.startswith("patenmatch"):
                continue  # TODO: for now skip patenmatch tests, they require a different User-type

            print("Sending Email '{}'".format(template_name))

            template_config = EMAILS_CONFIG.emails.get(template_name)
            template_info = get_full_template_info(template_config)

            mock_context = {}

            for dep in template_info["dependencies"]:
                context_dependent = dep.get("context_dependent", False)
                if context_dependent:
                    mock_context[dep["query_id_field"]] = dep["query_id_field"]

            mock_user_id = u1.id
            mock_match_id = match.id
            mock_proposed_match_id = proposal.id

            rendered = render_template_dynamic_lookup(
                template_name, mock_user_id, mock_match_id, mock_proposed_match_id, **mock_context
            )

            for key in mock_context:
                assert key in rendered, f"Key {key} not found in rendered email"
