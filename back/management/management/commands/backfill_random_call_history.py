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

Retroactive e-mails
-------------------
Every stored field this command fills is also an e-mail trigger, so a plain backfill mails
people about history that is months old. Two families need guarding, and both are guarded
by default.

**Milestones (m043/m044/m045).** Adoption sets ``completed_5/8/10_video_calls`` but leaves
``auto_email_m043/044/045_send`` at False. That combination is what the m043 query selects,
so a plain backfill would send "congrats on your 5th video call" retroactively to every pair
that already passed five calls and interacted within the last week — and would permanently
exclude pairs already past eight, because m044 and m045 each require the previous flag to be
True.

**The no-video-call ladder (m031/m032/m033/m042).** These select on ``first_interaction_at``
with ``total_mutal_video_calls_counter=0``. Filling ``first_interaction_at`` from lobby
history therefore drops a pair straight into whichever stage their age lands in — and m042
has *no upper bound*, so every pair whose lobby chat is older than 30 days qualifies at once.
This is what happened on 2026-08-27: 110 journey e-mails went out in one run, one person
receiving eleven.

Both guards mark only the stages the pair has *already* passed, which suppresses the
retroactive send while leaving the chain intact — a pair on six calls gets m043 marked and
m044 left alone, so m044 still fires at eight; a pair whose first interaction was 10 days ago
gets m031 marked and m032 left alone, so m032 still fires on day 14.

The ladder guard applies only to matches where *this run* filled ``first_interaction_at``. A
match that already had one was already in the ladder, and its flags already reflect what it
has been sent.

``--allow-milestone-emails`` and ``--allow-journey-emails`` skip the respective guard.

Dry run by default; pass ``--apply`` to write.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from management.models.matches import Match, MatchType

# Counter threshold → the flag adoption sets → the flag that stops the mail re-sending.
MILESTONES = (
    (5, "completed_5_video_calls", "auto_email_m043_send"),
    (8, "completed_8_video_calls", "auto_email_m044_send"),
    (10, "completed_10_video_calls", "auto_email_m045_send"),
)

# Days since `first_interaction_at` → the flag that stops that stage re-sending. Mirrors the
# windows in `automatic_emails_m031_m032_m033_m042`; m042 is the unbounded tail.
JOURNEY_STAGES = (
    (7, "auto_email_m031_send"),
    (14, "auto_email_m032_send"),
    (21, "auto_email_m033_send"),
    (30, "auto_email_m042_send"),
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
        parser.add_argument(
            "--allow-journey-emails",
            action="store_true",
            help=(
                "Leave the auto_email_m031/032/033/042 flags alone. Pairs whose first_interaction_at "
                "this run fills may then receive the no-video-call ladder retroactively — m042 has no "
                "upper bound, so that reaches every pair whose lobby chat is over 30 days old."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]
        batch_size = options["batch_size"]
        guard_emails = not options["allow_milestone_emails"]
        guard_journey = not options["allow_journey_emails"]

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
            "journey_stages_pre_armed": 0,
            "journey_matches_pre_armed": 0,
        }

        for batch in self._batches(candidates, batch_size):
            with transaction.atomic():
                for match in batch:
                    self._process(match, stats, guard_emails, guard_journey)
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

        if guard_journey:
            self.stdout.write(
                f"  ladder stages marked already sent ... {stats['journey_stages_pre_armed']} "
                f"across {stats['journey_matches_pre_armed']} matches "
                "(suppresses retroactive m031/m032/m033/m042)"
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "  no-video-call ladder guard DISABLED — every match whose first_interaction_at "
                    "this run fills may receive m031/m032/m033/m042 retroactively."
                )
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

    def _process(self, match, stats, guard_emails, guard_journey):
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

        # Only when *this* run filled it: a match that already had `first_interaction_at`
        # was already in the ladder, and its flags already say what it has been sent.
        filled_first_interaction = not had_first_interaction and match.first_interaction_at is not None
        if guard_journey and filled_first_interaction:
            armed = self._pre_arm_journey_stages(match)
            if armed:
                stats["journey_stages_pre_armed"] += armed
                stats["journey_matches_pre_armed"] += 1

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

    def _pre_arm_journey_stages(self, match):
        """Mark no-video-call stages the pair has already passed as sent.

        The ladder selects on ``first_interaction_at`` age with
        ``total_mutal_video_calls_counter=0``, so a pair that already has a mutual call can
        never receive it and needs no guard — checking that keeps the reported number equal
        to the e-mails actually suppressed rather than to rows touched.

        Only stages already passed are marked, so the ladder still picks up where the pair
        actually is: a first interaction 10 days old gets m031 marked and m032 left alone,
        and m032 fires normally on day 14.
        """
        if match.total_mutal_video_calls_counter:
            return 0
        if match.first_interaction_at is None:
            return 0

        age_days = (timezone.now() - match.first_interaction_at).days
        changed = []
        for threshold, send_field in JOURNEY_STAGES:
            if age_days >= threshold and not getattr(match, send_field):
                setattr(match, send_field, True)
                changed.append(send_field)

        if changed:
            match.save(update_fields=[*changed, "updated_at"])
        return len(changed)
