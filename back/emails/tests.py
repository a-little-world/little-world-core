from django.test import TestCase
from management.tests.helpers import register_user
from emails.api_v2.emails_config import EMAILS_CONFIG, EmailsConfig
from emails.api_v2.render_template import prepare_template_context, render_template_to_html, get_full_template_info
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
            
            template_info, context = prepare_template_context(template_name, u1.id, match.id)
            
            # We should check all the used template variables and if they are correctly injected
            email_html = render_template_to_html(template_info['config']['template'], context)