from django.test import TestCase
from management.tests.helpers import register_user
from emails.api_v2.emails_config import EMAILS_CONFIG
from emails.api_v2.render_template import get_full_template_info, render_template_dynamic_lookup
from management.controller import match_users, create_user_matching_proposal


class EmailTests(TestCase):
    def test_send_all_emails(self):
        # Test sending all emails
        u1 = register_user()
        u2 = register_user()
        u3 = register_user()

        match = match_users({u1, u2})
        proposal = create_user_matching_proposal({u1, u3}, send_confirm_match_email=False)

        for template_name in EMAILS_CONFIG.emails:
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

            rendered = render_template_dynamic_lookup(template_name, mock_user_id, mock_match_id, mock_proposed_match_id, **mock_context)

            for key in mock_context:
                assert key in rendered, f"Key {key} not found in rendered email"
