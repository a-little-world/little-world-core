"""Prevent M022 from being sent retroactively for existing conversations.

Dry run by default; pass ``--apply`` to mark every existing chat that already contains
at least one message as having completed the one-day reminder stage. Existing empty chats
remain untouched so a future first message can enter the M022/M023 sequence normally.
"""

from chat.models import Chat, Message
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef


class Command(BaseCommand):
    help = "Mark existing conversations as already processed for M022. Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the changes. Without this the command only reports what it would do.",
        )

    def handle(self, *args, **options):
        existing_message = Message.objects.filter(chat_id=OuterRef("pk"))
        candidates = Chat.objects.filter(one_day_inactive_email_send=False).annotate(
            _has_message=Exists(existing_message)
        )
        candidates = candidates.filter(_has_message=True)
        candidate_count = candidates.count()

        if options["apply"]:
            updated = candidates.update(one_day_inactive_email_send=True)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated {updated} existing chats. They will not receive a retroactive M022 reminder."
                )
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"Dry run: {candidate_count} existing chats would be marked as processed for M022. "
                "Re-run with --apply to write the changes."
            )
        )
