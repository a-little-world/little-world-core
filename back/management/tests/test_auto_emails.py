from datetime import timedelta

from django.test import TestCase
from django.utils import timezone as dj_timezone
from freezegun import freeze_time

from management.random_test_users import create_test_user
from management.tasks import automatic_emails_u023_u024_u025


class TestAutomaticEmails_023_024_025(TestCase):
    def setUp(self):
        self.simulation_date = dj_timezone.now() - timedelta(weeks=4)

        with freeze_time(self.simulation_date):
            self.valid_user_023 = create_test_user(20000, None, "Test123!", "email-test-valid-023@test.de")
            self.valid_user_024 = create_test_user(20001, None, "Test123!", "email-test-valid-024@test.de")
            self.valid_user_025 = create_test_user(20002, None, "Test123!", "email-test-valid-025@test.de")

            self.invalid_user_023_1 = create_test_user(20003, None, "Test123!", "email-test-invalid-023-1@test.de")
            self.invalid_user_023_2 = create_test_user(20004, None, "Test123!", "email-test-invalid-023-2@test.de")
            self.invalid_user_023_3 = create_test_user(20004, None, "Test123!", "email-test-invalid-023-3@test.de")

            self.invalid_user_024_1 = create_test_user(20005, None, "Test123!", "email-test-invalid-024-1@test.de")
            self.invalid_user_024_2 = create_test_user(20006, None, "Test123!", "email-test-invalid-024-2@test.de")
            self.invalid_user_024_3 = create_test_user(20007, None, "Test123!", "email-test-invalid-024-3@test.de")

            self.invalid_user_025_1 = create_test_user(20008, None, "Test123!", "email-test-invalid-025-1@test.de")
            self.invalid_user_025_2 = create_test_user(20009, None, "Test123!", "email-test-invalid-025-2@test.de")
            self.invalid_user_025_3 = create_test_user(200010, None, "Test123!", "email-test-invalid-025-3@test.de")

        # setup valid user exmaples
        self.valid_user_023.state.user_form_completed_at = dj_timezone.now() - timedelta(days=4)
        self.valid_user_024.state.user_form_completed_at = dj_timezone.now() - timedelta(days=8)
        self.valid_user_025.state.user_form_completed_at = dj_timezone.now() - timedelta(days=15)

        self.valid_user_023.state.had_prematching_call = False
        self.valid_user_024.state.had_prematching_call = False
        self.valid_user_025.state.had_prematching_call = False

        self.valid_user_024.state.user_form_completed_3_days_reminder_send = True
        self.valid_user_025.state.user_form_completed_3_days_reminder_send = True

        self.valid_user_025.state.user_form_completed_7_days_reminder_send = True

        self.valid_user_023.state.save()
        self.valid_user_024.state.save()
        self.valid_user_025.state.save()

        # setup invalid user examples for 023
        self.invalid_user_023_1.state.user_form_completed_at = dj_timezone.now() - timedelta(days=2)
        self.invalid_user_023_2.state.user_form_completed_at = dj_timezone.now() - timedelta(days=4)
        self.invalid_user_023_3.state.user_form_completed_at = dj_timezone.now() - timedelta(days=6)

        self.invalid_user_023_1.state.had_prematching_call = False
        self.invalid_user_023_2.state.had_prematching_call = False
        self.invalid_user_023_3.state.had_prematching_call = True

        self.invalid_user_023_2.state.user_form_completed_3_days_reminder_send = True

        self.invalid_user_023_1.state.save()
        self.invalid_user_023_2.state.save()
        self.invalid_user_023_3.state.save()

        # setup invalid user examples for 024
        self.invalid_user_024_1.state.user_form_completed_at = dj_timezone.now() - timedelta(days=2)
        self.invalid_user_024_2.state.user_form_completed_at = dj_timezone.now() - timedelta(days=4)
        self.invalid_user_024_3.state.user_form_completed_at = dj_timezone.now() - timedelta(days=8)

        self.invalid_user_024_1.state.had_prematching_call = True
        self.invalid_user_024_2.state.had_prematching_call = False
        self.invalid_user_024_3.state.had_prematching_call = False

        self.invalid_user_024_1.state.user_form_completed_3_days_reminder_send = True
        self.invalid_user_024_2.state.user_form_completed_3_days_reminder_send = True
        self.invalid_user_024_3.state.user_form_completed_7_days_reminder_send = True

        self.invalid_user_024_1.state.save()
        self.invalid_user_024_2.state.save()
        self.invalid_user_024_3.state.save()

        # setup invalid user examples for 025
        self.invalid_user_025_1.state.user_form_completed_at = dj_timezone.now() - timedelta(days=2)
        self.invalid_user_025_2.state.user_form_completed_at = dj_timezone.now() - timedelta(days=8)
        self.invalid_user_025_3.state.user_form_completed_at = dj_timezone.now() - timedelta(days=15)

        self.invalid_user_025_1.state.had_prematching_call = False
        self.invalid_user_025_2.state.had_prematching_call = False
        self.invalid_user_025_3.state.had_prematching_call = False

        self.invalid_user_025_1.state.user_form_completed_3_days_reminder_send = True
        self.invalid_user_025_2.state.user_form_completed_7_days_reminder_send = True
        self.invalid_user_025_3.state.user_form_completed_7_days_reminder_send = True

        self.invalid_user_025_1.state.save()
        self.invalid_user_025_2.state.save()
        self.invalid_user_025_3.state.save()

    def test_u023_u024_u025(self):
        u023_res = automatic_emails_u023_u024_u025(True)

        valids_023 = u023_res["users_u023"]
        valids_024 = u023_res["users_u024"]
        valids_025 = u023_res["users_u025"]

        assert len(valids_023) == 1
        assert len(valids_024) == 1
        assert len(valids_025) == 1

        assert valids_023[0] == self.valid_user_023
        assert valids_024[0] == self.valid_user_024
        assert valids_025[0] == self.valid_user_025
