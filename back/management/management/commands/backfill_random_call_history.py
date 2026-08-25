"""Adopt pre-existing lobby history onto Random Call matches created before it was done.

Why this exists: a Random Call match is made *after* the pair's lobby call, so its
counters and interaction timestamps have to be copied from the pair's existing history.
``Match.adopt_preexisting_pair_history()`` does that, but it is only called from
``controller.match_users()`` at creation time — every Random Call match that predates it
still carries zero counters and an empty ``first_interaction_at``.

Nothing repairs them passively. ``sync_counters`` is a management command, not a
``@shared_task``, so celery beat cannot schedule it; the only automatic path is the
m043/m044/m045 counter sync, whose querysets require ``confirmed=True``, ``active=True``
and a specific combination of e-mail flags, so it never reaches most of these rows.

The analytics side needs no backfill. Token counting, the match-journey video-path test
and every ``Match.journey()`` filter read live from ``LivekitSession`` / ``Message`` on
each query, so they already account for lobby history. What is stale here is the
*stored* state: the call/message counters, the three ``completed_*_video_calls`` flags
and ``first_interaction_at``.

Milestone e-mails
-----------------
Adoption sets ``completed_5/8/10_video_calls`` but leaves ``auto_email_m043/044/045_send``
at False. That combination is what the m043 query selects, so a plain backfill would send
"congrats on your 5th video call" retroactively to every pair that already passed five
calls and interacted within the last week — and would permanently exclude pairs already
past eight, because m044 and m045 each require the previous flag to be True.

By default this command therefore marks milestones the pair has *already* passed as
already sent. That suppresses the retroactive send and leaves the chain consistent, so
the next milestone still fires normally. Pass ``--allow-milestone-emails`` to skip the
guard and let those e-mails go out.

Dry run by default; pass ``--apply`` to write.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from management.models.matches import Match, MatchType

# Counter threshold → the flag adoption sets → the flag that stops the mail re-sending.
MILESTONES = (
    (5, "completed_5_video_calls", "auto_email_m043_send"),
    (8, "completed_8_video_calls", "auto_email_m044_send"),
    (10, "completed_10_video_calls", "auto_email_m045_send"),
)


class Command(BaseCommand):
    help = "Copy pre-existing lobby history onto Random Call matches. Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the changes. Without this the command only reports what it would do.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only consider the first N matches (oldest first). Useful for a cautious first pass.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Matches per transaction when applying (default 500).",
        )
        parser.add_argument(
            "--allow-milestone-emails",
            action="store_true",
            help=(
                "Leave the auto_email_m043/044/045 flags alone. Pairs already past a milestone "
                "may then receive that milestone's e-mail retroactively."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]
        batch_size = options["batch_size"]
        guard_emails = not options["allow_milestone_emails"]

        candidates = Match.objects.filter(match_type=MatchType.RANDOM_CALL).order_by("id")
        if limit:
            candidates = candidates[:limit]

        total = candidates.count() if limit is None else len(candidates)
        self.stdout.write(f"Examining {total} Random Call matches.")

        stats = {
            "touched": 0,
            "already_correct": 0,
            "no_history": 0,
            "first_interaction_set": 0,
            "milestones_pre_armed": 0,
        }

        for batch in self._batches(candidates, batch_size):
            with transaction.atomic():
                for match in batch:
                    self._process(match, stats, guard_emails)
                if not apply_changes:
                    transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Result" if apply_changes else "Dry run — nothing written"))
        self.stdout.write(f"  matches updated ..................... {stats['touched']}")
        self.stdout.write(f"    first_interaction_at filled ...... {stats['first_interaction_set']}")
        self.stdout.write(f"  already correct ..................... {stats['already_correct']}")
        self.stdout.write(f"  no pair history to adopt ............ {stats['no_history']}")

        if guard_emails:
            self.stdout.write(
                f"  milestones marked already sent ...... {stats['milestones_pre_armed']} "
                "(suppresses retroactive m043/m044/m045)"
            )
        else:
            self.stdout.write(
                self.style.WARNING("  milestone e-mail guard DISABLED — passed milestones may send retroactively.")
            )

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Re-run with --apply to write these changes."))

    # -- internals ---------------------------------------------------------

    def _batches(self, queryset, batch_size):
        batch = []
        for match in queryset.iterator(chunk_size=batch_size):
            batch.append(match)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def _process(self, match, stats, guard_emails):
        before = (
            match.total_messages_counter,
            match.total_mutal_video_calls_counter,
            match.first_interaction_at,
            match.latest_interaction_at,
        )
        had_first_interaction = match.first_interaction_at is not None

        # Idempotent: recomputes from the source rows every time, and only fills
        # `first_interaction_at` when it is still empty.
        match.adopt_preexisting_pair_history()

        if guard_emails:
            stats["milestones_pre_armed"] += self._pre_arm_milestones(match)

        if not (match.total_messages_counter or match.total_mutal_video_calls_counter):
            stats["no_history"] += 1
            return

        after = (
            match.total_messages_counter,
            match.total_mutal_video_calls_counter,
            match.first_interaction_at,
            match.latest_interaction_at,
        )
        if before == after:
            stats["already_correct"] += 1
            return

        stats["touched"] += 1
        if not had_first_interaction and match.first_interaction_at is not None:
            stats["first_interaction_set"] += 1

    def _pre_arm_milestones(self, match):
        """Mark milestones the pair already passed as sent, so they do not fire now.

        Only milestones actually reached are marked, which keeps the m043 → m044 → m045
        chain intact: a pair on six calls gets m043 marked and m044 left alone, so m044
        still sends when they reach eight.
        """
        changed = []
        for threshold, _reached_field, send_field in MILESTONES:
            if match.total_mutal_video_calls_counter >= threshold and not getattr(match, send_field):
                setattr(match, send_field, True)
                changed.append(send_field)

        if changed:
            match.save(update_fields=[*changed, "updated_at"])
        return len(changed)
