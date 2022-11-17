from django.test import TestCase


class EmailTests(TestCase):

    def test_send_email_dev(self):
        """
        test sending and email without sending and email
        by just generating the html for the template from dummy data
        """
        pass  # TODO

    def test_send_email_staging_test(self):
        # TODO: In the future this should be a *real* send email test
        # This should use safely modified stage_env params to send email to and test account
        # Then we should use some credentials to fetch that test email and see im e.g.: the registration code is correct
        pass

    def test_logging_email(self):
        pass  # TODO: test the creation of the 'email' model
