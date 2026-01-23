from datetime import timedelta

from chat.models import Chat, Message
from django.conf import settings
from django.db.models import Q
from django.test import TestCase
from django.utils import timezone as dj_timezone
from freezegun import freeze_time

from management.models.matches import Match
from management.models.state import State
from management.random_test_users import create_test_user
from management.tasks import (
    automatic_emails_m023,
    automatic_emails_m024_m025,
    automatic_emails_m12_m13_m14,
    automatic_emails_u023_u024_u025,
)


class TestAutomaticEmails_023_024_025(TestCase):
    def setUp(self):
        settings.DJANGO_TESTING = True

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
        u023_res = automatic_emails_u023_u024_u025()

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
        settings.DJANGO_TESTING = True

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
        result = automatic_emails_m12_m13_m14()

        valids_m12 = result["matches_m012"]
        valids_m13 = result["matches_m013"]
        valids_m14 = result["matches_m014"]

        assert len(valids_m12) == 1
        assert len(valids_m13) == 1
        assert len(valids_m14) == 1

        assert valids_m12[0].user1 == self.valid_user_m12 or valids_m12[0].user2 == self.valid_user_m12
        assert valids_m13[0].user1 == self.valid_user_m12 or valids_m13[0].user2 == self.valid_user_m13
        assert valids_m14[0].user1 == self.valid_user_m12 or valids_m14[0].user2 == self.valid_user_m14

        result = automatic_emails_m12_m13_m14()

        assert len(result["matches_m012"]) == 0
        assert len(result["matches_m013"]) == 0
        assert len(result["matches_m014"]) == 0


class TestAutomaticEmails_m023(TestCase):
    def setUp(self):
        settings.DJANGO_TESTING = True

        # Create regular users for valid chat (3+ days inactive)
        with freeze_time(dj_timezone.now() - timedelta(days=10)):
            self.valid_user_1 = create_test_user(30000, None, "Test123!", "m023-valid-user1@test.de")
            self.valid_user_2 = create_test_user(30001, None, "Test123!", "m023-valid-user2@test.de")

        # Create chat and message older than 3 days
        self.valid_chat = Chat.objects.create(u1=self.valid_user_1, u2=self.valid_user_2)
        with freeze_time(dj_timezone.now() - timedelta(days=4)):
            Message.objects.create(
                chat=self.valid_chat,
                sender=self.valid_user_1,
                recipient=self.valid_user_2,
                text="Hello, this is a test message",
            )

        # Create users for invalid chat (message too recent - only 2 days old)
        with freeze_time(dj_timezone.now() - timedelta(days=10)):
            self.invalid_user_1 = create_test_user(30002, None, "Test123!", "m023-invalid-user1@test.de")
            self.invalid_user_2 = create_test_user(30003, None, "Test123!", "m023-invalid-user2@test.de")

        self.invalid_chat_recent = Chat.objects.create(u1=self.invalid_user_1, u2=self.invalid_user_2)
        with freeze_time(dj_timezone.now() - timedelta(days=2)):
            Message.objects.create(
                chat=self.invalid_chat_recent,
                sender=self.invalid_user_1,
                recipient=self.invalid_user_2,
                text="Recent message",
            )

        # Create chat with staff user (should be excluded)
        with freeze_time(dj_timezone.now() - timedelta(days=10)):
            self.staff_user = create_test_user(30004, None, "Test123!", "m023-staff@test.de")
            self.staff_user.is_staff = True
            self.staff_user.save()
            self.normal_user_with_staff = create_test_user(30005, None, "Test123!", "m023-normal-with-staff@test.de")

        self.invalid_chat_staff = Chat.objects.create(u1=self.staff_user, u2=self.normal_user_with_staff)
        with freeze_time(dj_timezone.now() - timedelta(days=4)):
            Message.objects.create(
                chat=self.invalid_chat_staff,
                sender=self.staff_user,
                recipient=self.normal_user_with_staff,
                text="Staff message",
            )

        # Create chat with matching user (should be excluded)
        with freeze_time(dj_timezone.now() - timedelta(days=10)):
            self.matching_user = create_test_user(30006, None, "Test123!", "m023-matching@test.de")
            self.matching_user.state.extra_user_permissions = [State.ExtraUserPermissionChoices.MATCHING_USER]
            self.matching_user.state.save()
            self.normal_user_with_matching = create_test_user(
                30007, None, "Test123!", "m023-normal-with-matching@test.de"
            )

        self.invalid_chat_matching = Chat.objects.create(u1=self.matching_user, u2=self.normal_user_with_matching)
        with freeze_time(dj_timezone.now() - timedelta(days=4)):
            Message.objects.create(
                chat=self.invalid_chat_matching,
                sender=self.matching_user,
                recipient=self.normal_user_with_matching,
                text="Matching user message",
            )

        # Create chat with no messages (should be excluded)
        with freeze_time(dj_timezone.now() - timedelta(days=10)):
            self.no_msg_user_1 = create_test_user(30008, None, "Test123!", "m023-nomsg1@test.de")
            self.no_msg_user_2 = create_test_user(30009, None, "Test123!", "m023-nomsg2@test.de")

        self.invalid_chat_no_messages = Chat.objects.create(u1=self.no_msg_user_1, u2=self.no_msg_user_2)

    def test_m023_identifies_inactive_chats(self):
        result = automatic_emails_m023()

        inactive_chats = result["inactive_chats"]

        # Should only have the valid chat (3+ days inactive with regular users)
        assert len(inactive_chats) == 1
        assert inactive_chats[0] == self.valid_chat

        # Verify the flag was set
        self.valid_chat.refresh_from_db()
        assert self.valid_chat.three_days_inactive_email_send is True

        # Verify other chats weren't affected
        self.invalid_chat_recent.refresh_from_db()
        assert self.invalid_chat_recent.three_days_inactive_email_send is False

    def test_m023_excludes_staff_and_matching_users(self):
        result = automatic_emails_m023()

        inactive_chats = result["inactive_chats"]

        # Staff and matching user chats should not be in results
        assert self.invalid_chat_staff not in inactive_chats
        assert self.invalid_chat_matching not in inactive_chats

    def test_m023_does_not_resend(self):
        # First run
        result1 = automatic_emails_m023()
        assert len(result1["inactive_chats"]) == 1

        # Second run should find no new chats
        result2 = automatic_emails_m023()
        assert len(result2["inactive_chats"]) == 0


class TestAutomaticEmails_m024_m025(TestCase):
    def setUp(self):
        settings.DJANGO_TESTING = True

        # Create regular users for valid chat (7+ days inactive)
        with freeze_time(dj_timezone.now() - timedelta(days=14)):
            self.valid_user_1 = create_test_user(31000, None, "Test123!", "m024-valid-user1@test.de")
            self.valid_user_2 = create_test_user(31001, None, "Test123!", "m024-valid-user2@test.de")

        # Create chat and message older than 7 days
        self.valid_chat = Chat.objects.create(u1=self.valid_user_1, u2=self.valid_user_2)
        with freeze_time(dj_timezone.now() - timedelta(days=8)):
            Message.objects.create(
                chat=self.valid_chat,
                sender=self.valid_user_1,
                recipient=self.valid_user_2,
                text="Hello, this is a test message",
            )

        # Create users for invalid chat (message too recent - only 5 days old)
        with freeze_time(dj_timezone.now() - timedelta(days=14)):
            self.invalid_user_1 = create_test_user(31002, None, "Test123!", "m024-invalid-user1@test.de")
            self.invalid_user_2 = create_test_user(31003, None, "Test123!", "m024-invalid-user2@test.de")

        self.invalid_chat_recent = Chat.objects.create(u1=self.invalid_user_1, u2=self.invalid_user_2)
        with freeze_time(dj_timezone.now() - timedelta(days=5)):
            Message.objects.create(
                chat=self.invalid_chat_recent,
                sender=self.invalid_user_1,
                recipient=self.invalid_user_2,
                text="Recent message",
            )

        # Create chat with staff user (should be excluded)
        with freeze_time(dj_timezone.now() - timedelta(days=14)):
            self.staff_user = create_test_user(31004, None, "Test123!", "m024-staff@test.de")
            self.staff_user.is_staff = True
            self.staff_user.save()
            self.normal_user_with_staff = create_test_user(31005, None, "Test123!", "m024-normal-with-staff@test.de")

        self.invalid_chat_staff = Chat.objects.create(u1=self.staff_user, u2=self.normal_user_with_staff)
        with freeze_time(dj_timezone.now() - timedelta(days=8)):
            Message.objects.create(
                chat=self.invalid_chat_staff,
                sender=self.staff_user,
                recipient=self.normal_user_with_staff,
                text="Staff message",
            )

        # Create chat with matching user (should be excluded)
        with freeze_time(dj_timezone.now() - timedelta(days=14)):
            self.matching_user = create_test_user(31006, None, "Test123!", "m024-matching@test.de")
            self.matching_user.state.extra_user_permissions = [State.ExtraUserPermissionChoices.MATCHING_USER]
            self.matching_user.state.save()
            self.normal_user_with_matching = create_test_user(
                31007, None, "Test123!", "m024-normal-with-matching@test.de"
            )

        self.invalid_chat_matching = Chat.objects.create(u1=self.matching_user, u2=self.normal_user_with_matching)
        with freeze_time(dj_timezone.now() - timedelta(days=8)):
            Message.objects.create(
                chat=self.invalid_chat_matching,
                sender=self.matching_user,
                recipient=self.normal_user_with_matching,
                text="Matching user message",
            )

        # Create chat with no messages (should be excluded)
        with freeze_time(dj_timezone.now() - timedelta(days=14)):
            self.no_msg_user_1 = create_test_user(31008, None, "Test123!", "m024-nomsg1@test.de")
            self.no_msg_user_2 = create_test_user(31009, None, "Test123!", "m024-nomsg2@test.de")

        self.invalid_chat_no_messages = Chat.objects.create(u1=self.no_msg_user_1, u2=self.no_msg_user_2)

    def test_m024_m025_identifies_inactive_chats(self):
        result = automatic_emails_m024_m025()

        inactive_chats = result["inactive_chats"]

        # Should only have the valid chat (7+ days inactive with regular users)
        assert len(inactive_chats) == 1
        assert inactive_chats[0] == self.valid_chat

        # Verify the flag was set
        self.valid_chat.refresh_from_db()
        assert self.valid_chat.seven_days_inactive_email_send is True

        # Verify other chats weren't affected
        self.invalid_chat_recent.refresh_from_db()
        assert self.invalid_chat_recent.seven_days_inactive_email_send is False

    def test_m024_m025_excludes_staff_and_matching_users(self):
        result = automatic_emails_m024_m025()

        inactive_chats = result["inactive_chats"]

        # Staff and matching user chats should not be in results
        assert self.invalid_chat_staff not in inactive_chats
        assert self.invalid_chat_matching not in inactive_chats

    def test_m024_m025_does_not_resend(self):
        # First run
        result1 = automatic_emails_m024_m025()
        assert len(result1["inactive_chats"]) == 1

        # Second run should find no new chats
        result2 = automatic_emails_m024_m025()
        assert len(result2["inactive_chats"]) == 0
