from datetime import timedelta

from chat.models import Chat, Message
from django.test import TestCase
from django.utils import timezone

from management.api.user_report_utils import USER_EXPORT_COLUMN_NAMES, build_user_report_entry, datetime_to_readable_utc
from management.models.matches import Match
from management.models.user import User


class UserReportUtilsTests(TestCase):
    def test_build_user_report_entry_includes_latest_support_chat_messages(self):
        user = User.objects.create_user(
            email="support-export-user@example.com",
            username="support-export-user@example.com",
            password="Test123!",
        )
        support_user = User.objects.create_user(
            email="support-export-matcher@example.com",
            username="support-export-matcher@example.com",
            password="Test123!",
        )
        other_user = User.objects.create_user(
            email="support-export-other@example.com",
            username="support-export-other@example.com",
            password="Test123!",
        )

        Match.objects.create(user1=user, user2=support_user, active=True, support_matching=True)
        Match.objects.create(user1=user, user2=other_user, active=True, support_matching=False)

        support_chat = Chat.get_or_create_chat(user, support_user)
        other_chat = Chat.get_or_create_chat(user, other_user)
        now = timezone.now()

        ignored_regular_message = Message.objects.create(
            chat=other_chat,
            sender=user,
            recipient=other_user,
            text="regular match message",
        )
        ignored_regular_message.created = now + timedelta(minutes=4)
        ignored_regular_message.save(update_fields=["created"])

        first_user_message = Message.objects.create(
            chat=support_chat,
            sender=user,
            recipient=support_user,
            text="older support question",
        )
        first_user_message.created = now + timedelta(minutes=1)
        first_user_message.save(update_fields=["created"])

        support_reply = Message.objects.create(
            chat=support_chat,
            sender=support_user,
            recipient=user,
            text="latest support reply",
        )
        support_reply.created = now + timedelta(minutes=2)
        support_reply.save(update_fields=["created"])

        latest_user_message = Message.objects.create(
            chat=support_chat,
            sender=user,
            recipient=support_user,
            text="latest support question",
        )
        latest_user_message.created = now + timedelta(minutes=3)
        latest_user_message.save(update_fields=["created"])

        report_entry = build_user_report_entry(user)

        self.assertEqual(report_entry["last_user_to_support_message"], "latest support question")
        self.assertEqual(
            report_entry["last_user_to_support_message_time"],
            datetime_to_readable_utc(latest_user_message.created),
        )
        self.assertEqual(report_entry["last_support_to_user_reply"], "latest support reply")
        self.assertEqual(
            report_entry["last_support_to_user_reply_time"],
            datetime_to_readable_utc(support_reply.created),
        )
        self.assertIn("last_user_to_support_message", USER_EXPORT_COLUMN_NAMES)
        self.assertIn("last_user_to_support_message_time", USER_EXPORT_COLUMN_NAMES)
        self.assertIn("last_support_to_user_reply", USER_EXPORT_COLUMN_NAMES)
        self.assertIn("last_support_to_user_reply_time", USER_EXPORT_COLUMN_NAMES)
