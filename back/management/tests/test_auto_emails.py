from datetime import timedelta

from django.db.models import Q
from django.test import TestCase
from django.utils import timezone as dj_timezone
from freezegun import freeze_time

from management.models.matches import Match
from management.random_test_users import create_test_user
from management.tasks import automatic_emails_m12_m13_m14, automatic_emails_u023_u024_u025


class TestAutomaticEmails_023_024_025(TestCase):
    def setUp(self):
        self.simulation_date = dj_timezone.now() - timedelta(weeks=4)

        with freeze_time(self.simulation_date):
            self.valid_user_023 = create_test_user(20000, None, "Test123!", "email-test-valid-023@test.de")
            self.valid_user_024 = create_test_user(20001, None, "Test123!", "email-test-valid-024@test.de")
            self.valid_user_025 = create_test_user(20002, None, "Test123!", "email-test-valid-025@test.de")

            self.invalid_user_023_1 = create_test_user(20003, None, "Test123!", "email-test-invalid-023-1@test.de")
            self.invalid_user_023_2 = create_test_user(20004, None, "Test123!", "email-test-invalid-023-2@test.de")
            self.invalid_user_023_3 = create_test_user(20005, None, "Test123!", "email-test-invalid-023-3@test.de")

            self.invalid_user_024_1 = create_test_user(20006, None, "Test123!", "email-test-invalid-024-1@test.de")
            self.invalid_user_024_2 = create_test_user(20007, None, "Test123!", "email-test-invalid-024-2@test.de")
            self.invalid_user_024_3 = create_test_user(20008, None, "Test123!", "email-test-invalid-024-3@test.de")

            self.invalid_user_025_1 = create_test_user(20009, None, "Test123!", "email-test-invalid-025-1@test.de")
            self.invalid_user_025_2 = create_test_user(200010, None, "Test123!", "email-test-invalid-025-2@test.de")
            self.invalid_user_025_3 = create_test_user(200011, None, "Test123!", "email-test-invalid-025-3@test.de")

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


class TestAutomaticEmails_m12_m13_m14(TestCase):
    def setUp(self):
        self.simulation_date = dj_timezone.now() - timedelta(weeks=4)

        with freeze_time(dj_timezone.now() - timedelta(days=3)):
            self.valid_user_m12 = create_test_user(20000, None, "Test123!", "email-test-valid-023@test.de")

        with freeze_time(dj_timezone.now() - timedelta(days=9)):
            self.valid_user_m13 = create_test_user(20001, None, "Test123!", "email-test-valid-024@test.de")

        with freeze_time(dj_timezone.now() - timedelta(days=15)):
            self.valid_user_m14 = create_test_user(20002, None, "Test123!", "email-test-valid-025@test.de")

        with freeze_time(dj_timezone.now() - timedelta(days=4)):
            self.invalid_user_m12 = create_test_user(20003, None, "Test123!", "email-test-invalid-023@test.de")
            self.invalid_user_m13 = create_test_user(20004, None, "Test123!", "email-test-invalid-024@test.de")
            self.invalid_user_m14 = create_test_user(20005, None, "Test123!", "email-test-invalid-025@test.de")

        def confirm_all_matches_and_set_reminder_status(
            user, confirm=True, two_days=False, seven_days=False, fourteen_days=False
        ):
            valid_matches = Match.objects.filter(Q(user1=user, active=True) | Q(user2=user, active=True))

            for vm in valid_matches:
                vm.confirmed = confirm
                vm.interaction_reminder_2_days_send = two_days
                vm.interaction_reminder_7_days_send = seven_days
                vm.interaction_reminder_14_days_send = fourteen_days
                vm.save()

        confirm_all_matches_and_set_reminder_status(self.valid_user_m12, True, False, False, False)
        confirm_all_matches_and_set_reminder_status(self.valid_user_m13, True, True, False, False)
        confirm_all_matches_and_set_reminder_status(self.valid_user_m14, True, True, True, False)

        confirm_all_matches_and_set_reminder_status(self.invalid_user_m12, False, False, False, False)
        confirm_all_matches_and_set_reminder_status(self.invalid_user_m13, True, True, False, False)
        confirm_all_matches_and_set_reminder_status(self.invalid_user_m14, True, False, False, True)

    def test_m12_m13_m14(self):
        result = automatic_emails_m12_m13_m14(True)

        valids_m12 = result["matches_m012"]
        valids_m13 = result["matches_m013"]
        valids_m14 = result["matches_m014"]

        assert len(valids_m12) == 1
        assert len(valids_m13) == 1
        assert len(valids_m14) == 1

        assert valids_m12[0].user1 == self.valid_user_m12 or valids_m12[0].user2 == self.valid_user_m12
        assert valids_m13[0].user1 == self.valid_user_m12 or valids_m13[0].user2 == self.valid_user_m13
        assert valids_m14[0].user1 == self.valid_user_m12 or valids_m14[0].user2 == self.valid_user_m14

        result = automatic_emails_m12_m13_m14(True)

        assert len(result["matches_m012"]) == 0
        assert len(result["matches_m013"]) == 0
        assert len(result["matches_m014"]) == 0
