from datetime import timedelta
from unittest.mock import patch

from chat.models import Chat, Message
from django.conf import settings
from django.db.models import Q
from django.test import TestCase, override_settings
from django.utils import timezone as dj_timezone
from freezegun import freeze_time

from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.state import State
from management.random_test_users import create_test_user
from management.tasks import (
    automatic_emails_u051_u052,
    automatic_emails_m012_m013_m014,
    automatic_emails_m023,
    automatic_emails_m024_m025,
    automatic_emails_m031_m032_m033_m042,
    automatic_emails_u023_u024_u025,
    automatic_emails_u072_u073_u074,
    automatic_emails_u082_u083_u084,
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

        self.valid_user_023.state.is_onboarded = False
        self.valid_user_024.state.is_onboarded = False
        self.valid_user_025.state.is_onboarded = False

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

        self.invalid_user_023_1.state.is_onboarded = False
        self.invalid_user_023_2.state.is_onboarded = False
        self.invalid_user_023_3.state.is_onboarded = True

        self.invalid_user_023_2.state.user_form_completed_3_days_reminder_send = True

        self.invalid_user_023_1.state.save()
        self.invalid_user_023_2.state.save()
        self.invalid_user_023_3.state.save()

        # setup invalid user examples for 024
        self.invalid_user_024_1.state.user_form_completed_at = dj_timezone.now() - timedelta(days=2)
        self.invalid_user_024_2.state.user_form_completed_at = dj_timezone.now() - timedelta(days=4)
        self.invalid_user_024_3.state.user_form_completed_at = dj_timezone.now() - timedelta(days=8)

        self.invalid_user_024_1.state.is_onboarded = True
        self.invalid_user_024_2.state.is_onboarded = False
        self.invalid_user_024_3.state.is_onboarded = False

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

        self.invalid_user_025_1.state.is_onboarded = False
        self.invalid_user_025_2.state.is_onboarded = False
        self.invalid_user_025_3.state.is_onboarded = False

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
        result = automatic_emails_m012_m013_m014()

        valids_m12 = result["matches_m012"]
        valids_m13 = result["matches_m013"]
        valids_m14 = result["matches_m014"]

        assert len(valids_m12) == 1
        assert len(valids_m13) == 1
        assert len(valids_m14) == 1

        assert valids_m12[0].user1 == self.valid_user_m12 or valids_m12[0].user2 == self.valid_user_m12
        assert valids_m13[0].user1 == self.valid_user_m12 or valids_m13[0].user2 == self.valid_user_m13
        assert valids_m14[0].user1 == self.valid_user_m12 or valids_m14[0].user2 == self.valid_user_m14

        result = automatic_emails_m012_m013_m014()

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
        assert inactive_chats[0] == str(self.valid_chat.uuid)

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


class TestAutomaticEmails_m031_m032_m033_m042(TestCase):
    """Test for no video call reminders at 7, 14, 21, and 30 days."""

    def setUp(self):
        settings.DJANGO_TESTING = True

        # Create users for valid matches (one for each email tier)
        with freeze_time(dj_timezone.now() - timedelta(days=60)):
            # Valid match for m031 (7+ days, no video calls)
            self.valid_user_m031_1 = create_test_user(32000, None, "Test123!", "m031-valid-user1@test.de")
            self.valid_user_m031_2 = create_test_user(32001, None, "Test123!", "m031-valid-user2@test.de")

            # Valid match for m032 (14+ days, no video calls)
            self.valid_user_m032_1 = create_test_user(32002, None, "Test123!", "m032-valid-user1@test.de")
            self.valid_user_m032_2 = create_test_user(32003, None, "Test123!", "m032-valid-user2@test.de")

            # Valid match for m033 (21+ days, no video calls)
            self.valid_user_m033_1 = create_test_user(32004, None, "Test123!", "m033-valid-user1@test.de")
            self.valid_user_m033_2 = create_test_user(32005, None, "Test123!", "m033-valid-user2@test.de")

            # Invalid match - too recent (5 days)
            self.invalid_user_recent_1 = create_test_user(32006, None, "Test123!", "m031-invalid-recent1@test.de")
            self.invalid_user_recent_2 = create_test_user(32007, None, "Test123!", "m031-invalid-recent2@test.de")

            # Invalid match - has video calls
            self.invalid_user_video_1 = create_test_user(32008, None, "Test123!", "m031-invalid-video1@test.de")
            self.invalid_user_video_2 = create_test_user(32009, None, "Test123!", "m031-invalid-video2@test.de")

            # Valid match for m042 (confirmed, 30+ days since last interaction, no video calls)
            self.valid_user_m042_1 = create_test_user(32010, None, "Test123!", "m042-valid-user1@test.de")
            self.valid_user_m042_2 = create_test_user(32011, None, "Test123!", "m042-valid-user2@test.de")

            # Invalid match for m042 - not confirmed
            self.invalid_user_m042_unconfirmed_1 = create_test_user(
                32012, None, "Test123!", "m042-invalid-unconf1@test.de"
            )
            self.invalid_user_m042_unconfirmed_2 = create_test_user(
                32013, None, "Test123!", "m042-invalid-unconf2@test.de"
            )

            # Invalid match for m042 - recent interaction
            self.invalid_user_m042_recent_1 = create_test_user(32014, None, "Test123!", "m042-invalid-recent1@test.de")
            self.invalid_user_m042_recent_2 = create_test_user(32015, None, "Test123!", "m042-invalid-recent2@test.de")

        # Create valid match for m031 (first_interaction_at 8 days ago)
        self.valid_match_m031 = Match.objects.create(
            user1=self.valid_user_m031_1,
            user2=self.valid_user_m031_2,
            first_interaction_at=dj_timezone.now() - timedelta(days=8),
            total_mutal_video_calls_counter=0,
            auto_email_m031_send=False,
        )

        # Create valid match for m032 (first_interaction_at 15 days ago, m031 already sent)
        self.valid_match_m032 = Match.objects.create(
            user1=self.valid_user_m032_1,
            user2=self.valid_user_m032_2,
            first_interaction_at=dj_timezone.now() - timedelta(days=15),
            total_mutal_video_calls_counter=0,
            auto_email_m031_send=True,  # m031 already sent
            auto_email_m032_send=False,
        )

        # Create valid match for m033 (first_interaction_at 22 days ago, m031 and m032 already sent)
        self.valid_match_m033 = Match.objects.create(
            user1=self.valid_user_m033_1,
            user2=self.valid_user_m033_2,
            first_interaction_at=dj_timezone.now() - timedelta(days=22),
            total_mutal_video_calls_counter=0,
            auto_email_m031_send=True,  # m031 already sent
            auto_email_m032_send=True,  # m032 already sent
            auto_email_m033_send=False,
        )

        # Create invalid match - too recent (5 days)
        self.invalid_match_recent = Match.objects.create(
            user1=self.invalid_user_recent_1,
            user2=self.invalid_user_recent_2,
            first_interaction_at=dj_timezone.now() - timedelta(days=5),
            total_mutal_video_calls_counter=0,
            auto_email_m031_send=False,
        )

        # Create invalid match - has video calls
        self.invalid_match_video = Match.objects.create(
            user1=self.invalid_user_video_1,
            user2=self.invalid_user_video_2,
            first_interaction_at=dj_timezone.now() - timedelta(days=10),
            total_mutal_video_calls_counter=1,  # Has video calls
            auto_email_m031_send=False,
        )

        # Create valid match for m042 (confirmed, first_interaction_at 35 days ago, no video calls)
        self.valid_match_m042 = Match.objects.create(
            user1=self.valid_user_m042_1,
            user2=self.valid_user_m042_2,
            confirmed=True,
            first_interaction_at=dj_timezone.now() - timedelta(days=35),
            total_mutal_video_calls_counter=0,
            auto_email_m042_send=False,
        )

        # Create invalid match for m042 - recent interaction (only 20 days ago)
        self.invalid_match_m042_recent = Match.objects.create(
            user1=self.invalid_user_m042_recent_1,
            user2=self.invalid_user_m042_recent_2,
            confirmed=True,
            first_interaction_at=dj_timezone.now() - timedelta(days=20),
            total_mutal_video_calls_counter=0,
            auto_email_m042_send=False,
        )

    def test_identifies_correct_matches(self):
        """Test that the task identifies matches at correct time thresholds for all email types."""
        result = automatic_emails_m031_m032_m033_m042()

        matches_m031 = list(result["matches_m031"])
        matches_m032 = list(result["matches_m032"])
        matches_m033 = list(result["matches_m033"])
        matches_m042 = list(result["matches_m042"])

        # Valid matches should be included in their respective lists
        assert str(self.valid_match_m031.uuid) in matches_m031, (
            f"Valid match m031: {self.valid_match_m031.uuid}, matches_m031: {matches_m031}"
        )
        assert str(self.valid_match_m032.uuid) in matches_m032, (
            f"Valid match m032: {self.valid_match_m032.uuid}, matches_m032: {matches_m032}"
        )
        assert str(self.valid_match_m033.uuid) in matches_m033, (
            f"Valid match m033: {self.valid_match_m033.uuid}, matches_m033: {matches_m033}"
        )
        assert str(self.valid_match_m042.uuid) in matches_m042, (
            f"Valid match m042: {self.valid_match_m042.uuid}, matches_m042: {matches_m042}"
        )

        # Invalid matches should not be in any list
        assert str(self.invalid_match_recent.uuid) not in matches_m031, (
            f"Invalid match recent: {self.invalid_match_recent.uuid}, matches_m031: {matches_m031}"
        )
        assert str(self.invalid_match_video.uuid) not in matches_m031, (
            f"Invalid match video: {self.invalid_match_video.uuid}, matches_m031: {matches_m031}"
        )
        assert str(self.invalid_match_m042_recent.uuid) not in matches_m042, (
            f"Invalid match m042 recent: {self.invalid_match_m042_recent.uuid}, matches_m042: {matches_m042}"
        )

    def test_sets_flags_after_sending(self):
        """Test that the task sets the appropriate flags after sending."""
        automatic_emails_m031_m032_m033_m042()

        self.valid_match_m031.refresh_from_db()
        self.valid_match_m032.refresh_from_db()
        self.valid_match_m033.refresh_from_db()
        self.valid_match_m042.refresh_from_db()

        assert self.valid_match_m031.auto_email_m031_send is True
        assert self.valid_match_m032.auto_email_m032_send is True
        assert self.valid_match_m033.auto_email_m033_send is True
        assert self.valid_match_m042.auto_email_m042_send is True

    def test_does_not_resend(self):
        """Test that the task doesn't resend emails to matches that already received them."""
        # First run
        result1 = automatic_emails_m031_m032_m033_m042()
        print(result1)
        assert len(result1["matches_m031"]) > 0, f"Matches m031: {result1['matches_m031']}"
        assert len(result1["matches_m032"]) > 0, f"Matches m032: {result1['matches_m032']}"
        assert len(result1["matches_m033"]) > 0, f"Matches m033: {result1['matches_m033']}"
        assert len(result1["matches_m042"]) > 0, f"Matches m042: {result1['matches_m042']}"

        # Second run should find no new matches
        result2 = automatic_emails_m031_m032_m033_m042()
        assert len(result2["matches_m031"]) == 0, f"Matches m031: {result2['matches_m031']}"
        assert len(result2["matches_m032"]) == 0, f"Matches m032: {result2['matches_m032']}"
        assert len(result2["matches_m033"]) == 0, f"Matches m033: {result2['matches_m033']}"
        assert len(result2["matches_m042"]) == 0, f"Matches m042: {result2['matches_m042']}"

    def test_excludes_matches_with_video_calls(self):
        """Test that matches with video calls are excluded from all email types."""
        result = automatic_emails_m031_m032_m033_m042()

        matches_m031 = list(result["matches_m031"])

        # Match with video calls should be excluded
        assert str(self.invalid_match_video.uuid) not in matches_m031, (
            f"Invalid match video: {self.invalid_match_video.uuid}"
        )


class TestAutomaticEmails_u072_u073_u074(TestCase):
    """Test for users searching for the first time with no matching at 10, 21, and 30 days."""

    def setUp(self):
        settings.DJANGO_TESTING = True

        # Create valid users for each email tier
        with freeze_time(dj_timezone.now() - timedelta(days=60)):
            # Valid user for u072 (10-21 days after onboarding call)
            self.valid_user_u072 = create_test_user(33000, None, "Test123!", "u072-valid@test.de")

            # Valid user for u073 (21-30 days after onboarding call)
            self.valid_user_u073 = create_test_user(33001, None, "Test123!", "u073-valid@test.de")

            # Valid user for u074 (30+ days after onboarding call)
            self.valid_user_u074 = create_test_user(33002, None, "Test123!", "u074-valid@test.de")

            # Invalid user - too recent (only 5 days)
            self.invalid_user_recent = create_test_user(33003, None, "Test123!", "u072-invalid-recent@test.de")

            # Invalid user - has received first match
            self.invalid_user_has_match = create_test_user(33004, None, "Test123!", "u072-invalid-match@test.de")

            # Invalid user - not searching
            self.invalid_user_not_searching = create_test_user(33005, None, "Test123!", "u072-invalid-search@test.de")

            # Invalid user - email not authenticated
            self.invalid_user_no_email = create_test_user(33006, None, "Test123!", "u072-invalid-email@test.de")

        # Set up valid user u072 (onboarding completed 12 days ago)
        self.valid_user_u072.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=12)
        self.valid_user_u072.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.valid_user_u072.state.email_authenticated = True
        self.valid_user_u072.state.unresponsive = False
        self.valid_user_u072.state.is_onboarded = True
        self.valid_user_u072.state.has_received_first_match = False
        self.valid_user_u072.state.auto_email_u072_send = False
        self.valid_user_u072.state.save()

        # Set up valid user u073 (onboarding completed 23 days ago, u072 already sent)
        self.valid_user_u073.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=23)
        self.valid_user_u073.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.valid_user_u073.state.email_authenticated = True
        self.valid_user_u073.state.unresponsive = False
        self.valid_user_u073.state.is_onboarded = True
        self.valid_user_u073.state.has_received_first_match = False
        self.valid_user_u073.state.auto_email_u072_send = True  # u072 already sent
        self.valid_user_u073.state.auto_email_u073_send = False
        self.valid_user_u073.state.save()

        # Set up valid user u074 (onboarding completed 35 days ago, u072 and u073 already sent)
        self.valid_user_u074.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=35)
        self.valid_user_u074.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.valid_user_u074.state.email_authenticated = True
        self.valid_user_u074.state.unresponsive = False
        self.valid_user_u074.state.is_onboarded = True
        self.valid_user_u074.state.has_received_first_match = False
        self.valid_user_u074.state.auto_email_u072_send = True  # u072 already sent
        self.valid_user_u074.state.auto_email_u073_send = True  # u073 already sent
        self.valid_user_u074.state.auto_email_u074_send = False
        self.valid_user_u074.state.save()

        # Set up invalid user - too recent (5 days)
        self.invalid_user_recent.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=5)
        self.invalid_user_recent.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.invalid_user_recent.state.email_authenticated = True
        self.invalid_user_recent.state.unresponsive = False
        self.invalid_user_recent.state.is_onboarded = False
        self.invalid_user_recent.state.has_received_first_match = False
        self.invalid_user_recent.state.save()

        # Set up invalid user - has received first match
        self.invalid_user_has_match.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=12)
        self.invalid_user_has_match.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.invalid_user_has_match.state.email_authenticated = True
        self.invalid_user_has_match.state.unresponsive = False
        self.invalid_user_has_match.state.is_onboarded = True
        self.invalid_user_has_match.state.has_received_first_match = True  # Has match
        self.invalid_user_has_match.state.save()

        # Set up invalid user - not searching
        self.invalid_user_not_searching.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=12)
        self.invalid_user_not_searching.state.searching_state = State.SearchingStateChoices.IDLE  # Not searching
        self.invalid_user_not_searching.state.email_authenticated = True
        self.invalid_user_not_searching.state.unresponsive = False
        self.invalid_user_not_searching.state.is_onboarded = False
        self.invalid_user_not_searching.state.has_received_first_match = False
        self.invalid_user_not_searching.state.save()

        # Set up invalid user - email not authenticated
        self.invalid_user_no_email.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=12)
        self.invalid_user_no_email.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.invalid_user_no_email.state.email_authenticated = False  # Not authenticated
        self.invalid_user_no_email.state.unresponsive = False
        self.invalid_user_no_email.state.has_received_first_match = False
        self.invalid_user_no_email.state.save()

    def test_identifies_correct_users(self):
        """Test that the task identifies users at correct time thresholds for all email types."""
        result = automatic_emails_u072_u073_u074()

        users_u072 = list(result["users_u072"])
        users_u073 = list(result["users_u073"])
        users_u074 = list(result["users_u074"])

        # Valid users should be included in their respective lists
        assert self.valid_user_u072.hash in users_u072, (
            f"Valid user u072: {self.valid_user_u072.hash}, users_u072: {users_u072}"
        )
        assert self.valid_user_u073.hash in users_u073, (
            f"Valid user u073: {self.valid_user_u073.hash}, users_u073: {users_u073}"
        )
        assert self.valid_user_u074.hash in users_u074, (
            f"Valid user u074: {self.valid_user_u074.hash}, users_u074: {users_u074}"
        )

        # Invalid users should not be in any list
        assert self.invalid_user_recent.hash not in users_u072, f"Invalid user recent: {self.invalid_user_recent.hash}"
        assert self.invalid_user_has_match.hash not in users_u072, (
            f"Invalid user has match: {self.invalid_user_has_match.hash}"
        )
        assert self.invalid_user_not_searching.hash not in users_u072, (
            f"Invalid user not searching: {self.invalid_user_not_searching.hash}"
        )
        assert self.invalid_user_no_email.hash not in users_u072, (
            f"Invalid user no email: {self.invalid_user_no_email.hash}"
        )

    def test_sets_flags_after_sending(self):
        """Test that the task sets the appropriate flags after sending."""
        automatic_emails_u072_u073_u074()

        self.valid_user_u072.state.refresh_from_db()
        self.valid_user_u073.state.refresh_from_db()
        self.valid_user_u074.state.refresh_from_db()

        assert self.valid_user_u072.state.auto_email_u072_send is True
        assert self.valid_user_u073.state.auto_email_u073_send is True
        assert self.valid_user_u074.state.auto_email_u074_send is True

    def test_does_not_resend(self):
        """Test that the task doesn't resend emails to users that already received them."""
        # First run
        result1 = automatic_emails_u072_u073_u074()
        assert len(result1["users_u072"]) > 0, f"Users u072: {result1['users_u072']}"
        assert len(result1["users_u073"]) > 0, f"Users u073: {result1['users_u073']}"
        assert len(result1["users_u074"]) > 0, f"Users u074: {result1['users_u074']}"

        # Second run should find no new users
        result2 = automatic_emails_u072_u073_u074()
        assert len(result2["users_u072"]) == 0, f"Users u072: {result2['users_u072']}"
        assert len(result2["users_u073"]) == 0, f"Users u073: {result2['users_u073']}"
        assert len(result2["users_u074"]) == 0, f"Users u074: {result2['users_u074']}"

    def test_excludes_users_with_match(self):
        """Test that users who have received their first match are excluded."""
        result = automatic_emails_u072_u073_u074()

        users_u072 = list(result["users_u072"])

        # User with match should be excluded
        assert self.invalid_user_has_match.hash not in users_u072, (
            f"Invalid user has match: {self.invalid_user_has_match.hash}"
        )


class TestAutomaticEmails_u082_u083_u084(TestCase):
    """Test for users searching again with no matching at 10, 21, and 30 days (requires u081 sent first)."""

    def setUp(self):
        settings.DJANGO_TESTING = True

        # Create valid users for each email tier
        with freeze_time(dj_timezone.now() - timedelta(days=60)):
            # Valid user for u082 (10-21 days after onboarding call, u081 already sent)
            self.valid_user_u082 = create_test_user(34000, None, "Test123!", "u082-valid@test.de")

            # Valid user for u083 (21-30 days after onboarding call, u081 already sent)
            self.valid_user_u083 = create_test_user(34001, None, "Test123!", "u083-valid@test.de")

            # Valid user for u084 (30+ days after onboarding call, u081 already sent)
            self.valid_user_u084 = create_test_user(34002, None, "Test123!", "u084-valid@test.de")

            # Invalid user - u081 not sent
            self.invalid_user_no_u081 = create_test_user(34003, None, "Test123!", "u082-invalid-no-u081@test.de")

            # Invalid user - has not received first match
            self.invalid_user_no_match = create_test_user(34004, None, "Test123!", "u082-invalid-no-match@test.de")

            # Invalid user - too recent (only 5 days)
            self.invalid_user_recent = create_test_user(34005, None, "Test123!", "u082-invalid-recent@test.de")

        # Set up valid user u082 (onboarding completed 12 days ago, u081 sent)
        self.valid_user_u082.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=12)
        self.valid_user_u082.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.valid_user_u082.state.email_authenticated = True
        self.valid_user_u082.state.unresponsive = False
        self.valid_user_u082.state.is_onboarded = True
        self.valid_user_u082.state.has_received_first_match = True
        self.valid_user_u082.state.auto_emails_u081_send = True  # u081 sent
        self.valid_user_u082.state.auto_emails_u082_send = False
        self.valid_user_u082.state.save()

        # Set up valid user u083 (onboarding completed 23 days ago, u081 sent)
        self.valid_user_u083.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=23)
        self.valid_user_u083.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.valid_user_u083.state.email_authenticated = True
        self.valid_user_u083.state.unresponsive = False
        self.valid_user_u083.state.is_onboarded = True
        self.valid_user_u083.state.has_received_first_match = True
        self.valid_user_u083.state.auto_emails_u081_send = True  # u081 sent
        self.valid_user_u083.state.auto_emails_u082_send = True  # u082 already sent
        self.valid_user_u083.state.auto_emails_u083_send = False
        self.valid_user_u083.state.save()

        # Set up valid user u084 (onboarding completed 35 days ago, u081 sent)
        self.valid_user_u084.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=35)
        self.valid_user_u084.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.valid_user_u084.state.email_authenticated = True
        self.valid_user_u084.state.unresponsive = False
        self.valid_user_u084.state.is_onboarded = True
        self.valid_user_u084.state.has_received_first_match = True
        self.valid_user_u084.state.auto_emails_u081_send = True  # u081 sent
        self.valid_user_u084.state.auto_emails_u082_send = True  # u082 already sent
        self.valid_user_u084.state.auto_emails_u083_send = True  # u083 already sent
        self.valid_user_u084.state.auto_emails_u084_send = False
        self.valid_user_u084.state.save()

        # Set up invalid user - u081 not sent
        self.invalid_user_no_u081.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=12)
        self.invalid_user_no_u081.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.invalid_user_no_u081.state.email_authenticated = True
        self.invalid_user_no_u081.state.unresponsive = False
        self.invalid_user_no_u081.state.is_onboarded = True
        self.invalid_user_no_u081.state.has_received_first_match = True
        self.invalid_user_no_u081.state.auto_emails_u081_send = False  # u081 NOT sent
        self.invalid_user_no_u081.state.save()

        # Set up invalid user - has not received first match
        self.invalid_user_no_match.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=12)
        self.invalid_user_no_match.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.invalid_user_no_match.state.email_authenticated = True
        self.invalid_user_no_match.state.unresponsive = False
        self.invalid_user_no_match.state.is_onboarded = True
        self.invalid_user_no_match.state.has_received_first_match = False  # No match
        self.invalid_user_no_match.state.auto_emails_u081_send = True
        self.invalid_user_no_match.state.save()

        # Set up invalid user - too recent (5 days)
        self.invalid_user_recent.state.onboarding_call_completed_at = dj_timezone.now() - timedelta(days=5)
        self.invalid_user_recent.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.invalid_user_recent.state.email_authenticated = True
        self.invalid_user_recent.state.unresponsive = False
        self.invalid_user_recent.state.is_onboarded = True
        self.invalid_user_recent.state.has_received_first_match = True
        self.invalid_user_recent.state.auto_emails_u081_send = True
        self.invalid_user_recent.state.save()

    def test_identifies_correct_users(self):
        """Test that the task identifies users at correct time thresholds for all email types."""
        result = automatic_emails_u082_u083_u084()

        users_u082 = list(result["users_u082"])
        users_u083 = list(result["users_u083"])
        users_u084 = list(result["users_u084"])

        # Valid users should be included in their respective lists
        assert self.valid_user_u082.hash in users_u082, (
            f"Valid user u082: {self.valid_user_u082.hash}, users_u082: {users_u082}"
        )
        assert self.valid_user_u083.hash in users_u083, (
            f"Valid user u083: {self.valid_user_u083.hash}, users_u083: {users_u083}"
        )
        assert self.valid_user_u084.hash in users_u084, (
            f"Valid user u084: {self.valid_user_u084.hash}, users_u084: {users_u084}"
        )

        # Invalid users should not be in any list
        assert self.invalid_user_no_u081.hash not in users_u082, (
            f"Invalid user no u081: {self.invalid_user_no_u081.hash}"
        )
        assert self.invalid_user_no_match.hash not in users_u082, (
            f"Invalid user no match: {self.invalid_user_no_match.hash}"
        )
        assert self.invalid_user_recent.hash not in users_u082, f"Invalid user recent: {self.invalid_user_recent.hash}"

    def test_sets_flags_after_sending(self):
        """Test that the task sets the appropriate flags after sending."""
        automatic_emails_u082_u083_u084()

        self.valid_user_u082.state.refresh_from_db()
        self.valid_user_u083.state.refresh_from_db()
        self.valid_user_u084.state.refresh_from_db()

        assert self.valid_user_u082.state.auto_emails_u082_send is True
        assert self.valid_user_u083.state.auto_emails_u083_send is True
        assert self.valid_user_u084.state.auto_emails_u084_send is True

    def test_does_not_resend(self):
        """Test that the task doesn't resend emails to users that already received them."""
        # First run
        result1 = automatic_emails_u082_u083_u084()
        assert len(result1["users_u082"]) > 0, f"Users u082: {result1['users_u082']}"
        assert len(result1["users_u083"]) > 0, f"Users u083: {result1['users_u083']}"
        assert len(result1["users_u084"]) > 0, f"Users u084: {result1['users_u084']}"

        # Second run should find no new users
        result2 = automatic_emails_u082_u083_u084()
        assert len(result2["users_u082"]) == 0, f"Users u082: {result2['users_u082']}"
        assert len(result2["users_u083"]) == 0, f"Users u083: {result2['users_u083']}"
        assert len(result2["users_u084"]) == 0, f"Users u084: {result2['users_u084']}"

    def test_requires_u081_sent(self):
        """Test that users without u081 sent are excluded."""
        result = automatic_emails_u082_u083_u084()

        users_u082 = list(result["users_u082"])

        # User without u081 sent should be excluded
        assert self.invalid_user_no_u081.hash not in users_u082, (
            f"Invalid user no u081: {self.invalid_user_no_u081.hash}"
        )


class TestAutomaticEmails_u081(TestCase):
    """Test for u081 email trigger when user starts searching again after having a match."""

    def setUp(self):
        settings.DJANGO_TESTING = True

        with freeze_time(dj_timezone.now() - timedelta(days=30)):
            # User who should receive u081 (has match, searching again, u081 not sent)
            self.valid_user = create_test_user(35000, None, "Test123!", "u081-valid@test.de")

            # User who should NOT receive u081 (u081 already sent)
            self.invalid_user_already_sent = create_test_user(35001, None, "Test123!", "u081-already-sent@test.de")

            # User who should NOT receive u081 (no match yet)
            self.invalid_user_no_match = create_test_user(35002, None, "Test123!", "u081-no-match@test.de")

        # Set up valid user (has match, u081 not sent)
        self.valid_user.state.has_received_first_match = True
        self.valid_user.state.auto_emails_u081_send = False
        self.valid_user.state.searching_state = State.SearchingStateChoices.IDLE
        self.valid_user.state.save()

        # Set up invalid user (u081 already sent)
        self.invalid_user_already_sent.state.has_received_first_match = True
        self.invalid_user_already_sent.state.auto_emails_u081_send = True  # Already sent
        self.invalid_user_already_sent.state.searching_state = State.SearchingStateChoices.IDLE
        self.invalid_user_already_sent.state.save()

        # Set up invalid user (no match yet)
        self.invalid_user_no_match.state.has_received_first_match = False  # No match
        self.invalid_user_no_match.state.auto_emails_u081_send = False
        self.invalid_user_no_match.state.searching_state = State.SearchingStateChoices.IDLE
        self.invalid_user_no_match.state.save()

    @override_settings(ENABLE_AUTO_EMAILS__U081_U082_U083_U084=True)
    @patch("management.api.user.send_email_background")
    def test_sends_u081_when_user_starts_searching_again(self, mock_send_email):
        """Test that u081 is sent when user with match starts searching again."""
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.valid_user)

        response = client.post("/api/user/search_state/searching")

        assert response.status_code == 200

        # Verify email was sent
        mock_send_email.delay.assert_called_once()
        call_args = mock_send_email.delay.call_args
        assert call_args[0][0] == "automatic-emails-u081"
        assert call_args[1]["user_id"] == self.valid_user.id

        # Verify flag was set
        self.valid_user.state.refresh_from_db()
        assert self.valid_user.state.auto_emails_u081_send is True

    @override_settings(ENABLE_AUTO_EMAILS__U081_U082_U083_U084=True)
    @patch("management.api.user.send_email_background")
    def test_does_not_resend_u081(self, mock_send_email):
        """Test that u081 is not sent again if already sent."""
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.invalid_user_already_sent)

        response = client.post("/api/user/search_state/searching")

        assert response.status_code == 200

        # Verify email was NOT sent
        mock_send_email.delay.assert_not_called()

    @override_settings(ENABLE_AUTO_EMAILS__U081_U082_U083_U084=True)
    @patch("management.api.user.send_email_background")
    def test_does_not_send_u081_without_match(self, mock_send_email):
        """Test that u081 is not sent if user has not received first match."""
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.invalid_user_no_match)

        response = client.post("/api/user/search_state/searching")

        assert response.status_code == 200

        # Verify email was NOT sent
        mock_send_email.delay.assert_not_called()

    @override_settings(ENABLE_AUTO_EMAILS__U081_U082_U083_U084=False)
    @patch("management.api.user.send_email_background")
    def test_does_not_send_u081_when_feature_disabled(self, mock_send_email):
        """Test that u081 is not sent when the feature flag is disabled."""
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.valid_user)

        response = client.post("/api/user/search_state/searching")

        assert response.status_code == 200

        # Verify email was NOT sent (feature disabled)
        mock_send_email.delay.assert_not_called()

        # Verify flag was NOT set
        self.valid_user.state.refresh_from_db()
        assert self.valid_user.state.auto_emails_u081_send is False


class TestAutomaticEmails_m032_m033_m042_EmailContent(TestCase):
    """Test that m032, m033, and m042 emails contain correct still_in_contact URLs and redirect properly."""

    def setUp(self):
        settings.DJANGO_TESTING = True

        # Create users for testing email content
        with freeze_time(dj_timezone.now() - timedelta(days=60)):
            self.user1 = create_test_user(40000, None, "Test123!", "m032-content-user1@test.de")
            self.user2 = create_test_user(40001, None, "Test123!", "m032-content-user2@test.de")

        # Create a match for testing
        self.match = Match.objects.create(
            user1=self.user1,
            user2=self.user2,
            first_interaction_at=dj_timezone.now() - timedelta(days=15),
            total_mutal_video_calls_counter=0,
            auto_email_m031_send=True,
            auto_email_m032_send=False,
        )

    def _send_email_and_get_log(self, template_name, user, match, context):
        """Helper to send an emulated email and return the EmailLog."""
        from emails.api.send_email import send_template_email
        from emails.models import EmailLog

        # Send email with emulated_send=True
        send_template_email(
            template_name,
            user_id=user.id,
            match_id=match.id,
            emulated_send=True,
            context=context,
        )

        # Get the most recent EmailLog for this template and user
        return (
            EmailLog.objects.filter(
                template=template_name,
                receiver=user,
            )
            .order_by("-time")
            .first()
        )

    def test_m032_email_contains_still_in_contact_url(self):
        """Test that m032 email contains the correct still_in_contact URL."""

        context = {
            "redirect_slug_no": "info-screen",
            "redirect_slug_yes": "match-form1",
        }

        email_log = self._send_email_and_get_log(
            "automatic-emails-m032",
            self.user1,
            self.match,
            context,
        )

        assert email_log is not None, "EmailLog should be created"
        assert email_log.sucess is True, "Email should be sent successfully"
        assert "emulated_send" in email_log.data, "Email should be marked as emulated"

        # Verify the email HTML contains the still_in_contact URL
        email_html = email_log.data.get("html", "")

        # Check that the URL contains the correct match UUID
        expected_url_part = f"/api/still_in_contact/{str(self.match.uuid)}/yes/"
        assert expected_url_part in email_html, (
            f"Email should contain still_in_contact URL with match UUID. Expected: {expected_url_part}"
        )

        # Check that the URL contains the user hash
        assert f"user_hash={self.user1.hash}" in email_html, "Email should contain still_in_contact URL with user hash"

        # Check that the URL contains the user token
        assert f"user_token={self.user1.state.still_in_contact_form_access_token_user}" in email_html, (
            "Email should contain still_in_contact URL with user token"
        )

        # Check that the redirect_slug is correct for the yes case
        assert "redirect_slug=match-form1" in email_html, (
            "Email should contain redirect_slug=match-form1 for the yes URL"
        )

    def test_m033_email_contains_still_in_contact_url(self):
        """Test that m033 email contains the correct still_in_contact URL."""
        # Update match for m033 scenario
        self.match.first_interaction_at = dj_timezone.now() - timedelta(days=22)
        self.match.auto_email_m032_send = True
        self.match.auto_email_m033_send = False
        self.match.save()

        context = {
            "redirect_slug_no": "info-screen",
            "redirect_slug_yes": "match-form1",
        }

        email_log = self._send_email_and_get_log(
            "automatic-emails-m033",
            self.user1,
            self.match,
            context,
        )

        assert email_log is not None, "EmailLog should be created"
        assert email_log.sucess is True, "Email should be sent successfully"

        email_html = email_log.data.get("html", "")

        # Check that the URL contains the correct match UUID
        expected_url_part = f"/api/still_in_contact/{str(self.match.uuid)}/yes/"
        assert expected_url_part in email_html, "Email should contain still_in_contact URL with match UUID"

        # Check that the URL contains the user hash and token
        assert f"user_hash={self.user1.hash}" in email_html
        assert f"user_token={self.user1.state.still_in_contact_form_access_token_user}" in email_html

        # Check that the redirect_slug is correct
        assert "redirect_slug=match-form1" in email_html

    def test_m042_email_contains_still_in_contact_url(self):
        """Test that m042 email contains the correct still_in_contact URL."""
        # Update match for m042 scenario
        self.match.first_interaction_at = dj_timezone.now() - timedelta(days=35)
        self.match.confirmed = True
        self.match.auto_email_m042_send = False
        self.match.save()

        context = {
            "redirect_slug": "match-form1",
        }

        email_log = self._send_email_and_get_log(
            "automatic-emails-m042",
            self.user1,
            self.match,
            context,
        )

        assert email_log is not None, "EmailLog should be created"
        assert email_log.sucess is True, "Email should be sent successfully"

        email_html = email_log.data.get("html", "")

        # Check that the URL contains the correct match UUID
        expected_url_part = f"/api/still_in_contact/{str(self.match.uuid)}/yes/"
        assert expected_url_part in email_html, "Email should contain still_in_contact URL with match UUID"

        # Check that the URL contains the user hash and token
        assert f"user_hash={self.user1.hash}" in email_html
        assert f"user_token={self.user1.state.still_in_contact_form_access_token_user}" in email_html

    def test_still_in_contact_yes_redirects_to_google_form(self):
        """Test that the still_in_contact endpoint with answer='yes' and redirect_slug='match-form1' redirects to Google Form."""
        from rest_framework.test import APIClient

        client = APIClient()

        # Build the URL with proper parameters
        url = (
            f"/api/still_in_contact/{str(self.match.uuid)}/yes/"
            f"?user_hash={self.user1.hash}"
            f"&user_token={self.user1.state.still_in_contact_form_access_token_user}"
            f"&redirect_slug=match-form1"
        )

        response = client.get(url)

        # Should redirect (302 status code)
        assert response.status_code == 302, f"Expected redirect (302), got {response.status_code}"

        # Check the redirect URL is the Google Form
        redirect_url = response.url
        expected_google_form_base = (
            "https://docs.google.com/forms/d/e/1FAIpQLScZpHVBkd9oXMTXGwH6aIUS8-Ep3LGbmHzx0wKYTA0fDpzJtQ/viewform"
        )
        assert redirect_url.startswith(expected_google_form_base), (
            f"Expected redirect to Google Form. Got: {redirect_url}"
        )

        # Check that the redirect URL contains the user hash and match UUID as form pre-fill parameters
        assert f"entry.1868418501={self.user1.hash}" in redirect_url, (
            "Redirect URL should contain user hash as form parameter"
        )
        assert f"entry.1064841735={str(self.match.uuid)}" in redirect_url, (
            "Redirect URL should contain match UUID as form parameter"
        )

        # Verify the match was marked as completed_off_plattform
        self.match.refresh_from_db()
        assert self.match.completed_off_plattform is True

    def test_still_in_contact_no_shows_info_screen(self):
        """Test that the still_in_contact endpoint with redirect_slug='info-screen' shows info card."""
        from rest_framework.test import APIClient

        client = APIClient()

        # Build the URL with info-screen redirect
        url = (
            f"/api/still_in_contact/{str(self.match.uuid)}/no/"
            f"?user_hash={self.user1.hash}"
            f"&user_token={self.user1.state.still_in_contact_form_access_token_user}"
            f"&redirect_slug=info-screen"
        )

        response = client.get(url)

        # Should return 200 with info card content (not a redirect)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        # Verify the match was still marked as completed_off_plattform
        self.match.refresh_from_db()
        # Should be marked 'False' for the 'no' case
        assert self.match.completed_off_plattform is False

    def test_still_in_contact_rejects_invalid_token(self):
        """Test that the still_in_contact endpoint rejects requests with invalid user token."""
        from rest_framework.test import APIClient

        client = APIClient()

        # Build the URL with an invalid token
        url = (
            f"/api/still_in_contact/{str(self.match.uuid)}/yes/"
            f"?user_hash={self.user1.hash}"
            f"&user_token=invalid-token-12345"
            f"&redirect_slug=match-form1"
        )

        response = client.get(url)

        # Should return 403 Forbidden
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"

    def test_m032_m033_emails_sent_to_both_users(self):
        """Test that m032 emails are sent to both users in the match with correct URLs."""
        context = {
            "redirect_slug_no": "info-screen",
            "redirect_slug_yes": "match-form1",
        }

        # Send emails to both users
        email_log_user1 = self._send_email_and_get_log(
            "automatic-emails-m032",
            self.user1,
            self.match,
            context,
        )
        email_log_user2 = self._send_email_and_get_log(
            "automatic-emails-m032",
            self.user2,
            self.match,
            context,
        )

        # Verify both emails were created
        assert email_log_user1 is not None
        assert email_log_user2 is not None

        # Verify user1's email contains user1's hash
        email_html_user1 = email_log_user1.data.get("html", "")
        assert f"user_hash={self.user1.hash}" in email_html_user1

        # Verify user2's email contains user2's hash
        email_html_user2 = email_log_user2.data.get("html", "")
        assert f"user_hash={self.user2.hash}" in email_html_user2

        # Both emails should reference the same match UUID
        assert f"/api/still_in_contact/{str(self.match.uuid)}/yes/" in email_html_user1
        assert f"/api/still_in_contact/{str(self.match.uuid)}/yes/" in email_html_user2


class TestPrematchingCheckoffEmailQueue(TestCase):
    def setUp(self):
        settings.DJANGO_TESTING = True

        self.staff_user = create_test_user(41000, None, "Test123!", "prematch-staff@test.de")
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.attended_user_1 = create_test_user(41001, None, "Test123!", "prematch-attended-1@test.de")
        self.attended_user_2 = create_test_user(41002, None, "Test123!", "prematch-attended-2@test.de")
        self.no_show_user_1 = create_test_user(41003, None, "Test123!", "prematch-no-show-1@test.de")
        self.no_show_user_2 = create_test_user(41004, None, "Test123!", "prematch-no-show-2@test.de")

        for user in [self.attended_user_1, self.attended_user_2, self.no_show_user_1, self.no_show_user_2]:
            user.state.is_onboarded = False
            user.state.save()

        self.no_show_user_1.state.not_attended_auto_email_u053_send = True
        self.no_show_user_1.state.not_attended_auto_email_u054_send = False
        self.no_show_user_1.state.save()

        self.no_show_user_2.state.not_attended_auto_email_u053_send = True
        self.no_show_user_2.state.not_attended_auto_email_u054_send = True
        self.no_show_user_2.state.save()

        self.appointment_date = dj_timezone.now().replace(microsecond=0)
        end_time = self.appointment_date + timedelta(hours=1)

        for user in [self.attended_user_1, self.attended_user_2, self.no_show_user_1, self.no_show_user_2]:
            PreMatchingAppointment.objects.create(user=user, start_time=self.appointment_date, end_time=end_time)

    @patch("management.tasks.send_email_background")
    def test_prematching_checkoff_queue_and_requeue_behavior(self, mock_task_send_email):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.staff_user)

        payload = {
            "appointment_date": self.appointment_date.isoformat(),
            "selected_users": [self.attended_user_1.id, self.attended_user_2.id],
            "send_emails_now": False,
        }

        response = client.post("/api/matching/prematchingappointments/complete_prematching_call/", payload, format="json")
        assert response.status_code == 200
        assert response.data["unretrievable_user_ids"] == []

        for user in [self.attended_user_1, self.attended_user_2]:
            user.state.refresh_from_db()
            assert user.state.is_onboarded is True
            assert user.state.attended_auto_email_u051_send is False
            assert user.state.attended_auto_email_u051_send_at is None
            assert user.state.last_prematching_checkoff_at is not None

        for user in [self.no_show_user_1, self.no_show_user_2]:
            user.state.refresh_from_db()
            assert user.state.is_onboarded is False
            assert user.state.not_attended_auto_email_u052_send is False
            assert user.state.not_attended_auto_email_u052_send_at is None
            assert user.state.last_prematching_checkoff_at is not None

        assert self.no_show_user_1.state.not_attended_auto_email_u053_send is True
        assert self.no_show_user_1.state.not_attended_auto_email_u054_send is False
        assert self.no_show_user_2.state.not_attended_auto_email_u053_send is True
        assert self.no_show_user_2.state.not_attended_auto_email_u054_send is True

        report = automatic_emails_u051_u052()
        assert report["u051_count"] == 2
        assert report["u052_count"] == 2
        assert mock_task_send_email.delay.call_count == 4

        sent_templates = [call[0][0] for call in mock_task_send_email.delay.call_args_list]
        assert sent_templates.count("automatic-emails-u071") == 2
        assert sent_templates.count("prematching-call-no-show") == 2

        for user in [self.attended_user_1, self.attended_user_2]:
            user.state.refresh_from_db()
            assert user.state.attended_auto_email_u051_send is True
            assert user.state.attended_auto_email_u051_send_at is not None

        for user in [self.no_show_user_1, self.no_show_user_2]:
            user.state.refresh_from_db()
            assert user.state.not_attended_auto_email_u052_send is True
            assert user.state.not_attended_auto_email_u052_send_at is not None

        mock_task_send_email.reset_mock()

        # Running check-off again must not requeue attended users, but should requeue no-show users.
        response_repeat = client.post(
            "/api/matching/prematchingappointments/complete_prematching_call/", payload, format="json"
        )
        assert response_repeat.status_code == 200

        for user in [self.attended_user_1, self.attended_user_2]:
            user.state.refresh_from_db()
            assert user.state.is_onboarded is True
            assert user.state.attended_auto_email_u051_send is True

        for user in [self.no_show_user_1, self.no_show_user_2]:
            user.state.refresh_from_db()
            assert user.state.not_attended_auto_email_u052_send is False
            assert user.state.not_attended_auto_email_u052_send_at is None

        assert self.no_show_user_1.state.not_attended_auto_email_u053_send is True
        assert self.no_show_user_1.state.not_attended_auto_email_u054_send is False
        assert self.no_show_user_2.state.not_attended_auto_email_u053_send is True
        assert self.no_show_user_2.state.not_attended_auto_email_u054_send is True

        report_repeat = automatic_emails_u051_u052()
        assert report_repeat["u051_count"] == 0
        assert report_repeat["u052_count"] == 2
        assert mock_task_send_email.delay.call_count == 2
        sent_templates_repeat = [call[0][0] for call in mock_task_send_email.delay.call_args_list]
        assert sent_templates_repeat == ["prematching-call-no-show", "prematching-call-no-show"]

        mock_task_send_email.reset_mock()
        report_third_run = automatic_emails_u051_u052()
        assert report_third_run["u051_count"] == 0
        assert report_third_run["u052_count"] == 0
        mock_task_send_email.delay.assert_not_called()

    def test_prematching_checkoff_collects_unretrievable_selected_users(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.staff_user)

        missing_id = 9999999
        payload = {
            "appointment_date": self.appointment_date.isoformat(),
            "selected_users": [self.attended_user_1.id, missing_id],
            "send_emails_now": False,
        }

        response = client.post("/api/matching/prematchingappointments/complete_prematching_call/", payload, format="json")
        assert response.status_code == 200
        assert response.data["unretrievable_user_ids"] == [missing_id]

        self.attended_user_1.state.refresh_from_db()
        assert self.attended_user_1.state.is_onboarded is True
        assert self.attended_user_1.state.last_prematching_checkoff_at is not None

    @patch("management.tasks.automatic_emails_u051_u052")
    def test_prematching_checkoff_can_trigger_send_now(self, mock_u051_u052_task):
        from types import SimpleNamespace

        from rest_framework.test import APIClient

        mock_u051_u052_task.delay.return_value = SimpleNamespace(id="task-u051-u052-1")

        client = APIClient()
        client.force_authenticate(user=self.staff_user)

        payload = {
            "appointment_date": self.appointment_date.isoformat(),
            "selected_users": [self.attended_user_1.id, self.attended_user_2.id],
            "send_emails_now": True,
        }

        response = client.post("/api/matching/prematchingappointments/complete_prematching_call/", payload, format="json")
        assert response.status_code == 200
        assert response.data["send_emails_now"] is True
        assert response.data["send_task_id"] == "task-u051-u052-1"
        mock_u051_u052_task.delay.assert_called_once()
