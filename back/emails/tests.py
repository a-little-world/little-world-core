from django.test import TestCase
from management.tests.helpers import register_user
from emails.api_v2.emails_config import EMAILS_CONFIG, EmailsConfig
from emails.api_v2.render_template import prepare_template_context, render_template_to_html, get_full_template_info, render_template_dynamic_lookup
from management.controller import match_users


class EmailTests(TestCase):

    def test_send_all_emails(self):
        # Test sending all emails
        u1 = register_user()
        u2 = register_user()
        
        match = match_users({
            u1, u2
        })
        
        for template_name in EMAILS_CONFIG.emails:
            print("Sending Email '{}'".format(template_name))
            
            template_config = EMAILS_CONFIG.emails.get(template_name)
            template_info = get_full_template_info(template_config)
            
            mock_context = {}

            for dep in template_info['dependencies']:
                context_dependent = dep.get("context_dependent", False)
                if context_dependent:
                    mock_context[dep["query_id_field"]] = "Mocked value"
            
            mock_user_id = u1.id
            mock_match_id = match.id
            
            rendered = render_template_dynamic_lookup(template_name, mock_user_id, mock_match_id, **mock_context)