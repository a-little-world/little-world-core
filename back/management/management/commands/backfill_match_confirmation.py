"""Repair `Match.confirmed` / `Match.confirmed_by` from evidence of mutual contact.

Why this exists: `confirmed_by` was written by the frontend, and only when a user happened
to open the new-match card. Matches where that never fired are stuck with an incomplete
`confirmed_by` — on the dev database, 175 confirmed matches have *no* entries at all and
220 have only one. `Match.get_confirmed_matches()` filters on `confirmed_by=user`, so
those matches are missing from one or both partners' confirmed list.

Nothing repairs them passively. The periodic counter sync is the only automatic path and
its querysets all filter `confirmed=True`, so it can never reach a row the flag is wrong
on; the message hook only fires when someone sends a *new* message, which never happens
for a match that has gone quiet.

Evidence used, deliberately conservative:

* a user goes into ``confirmed_by`` when they demonstrably engaged — they sent a message
  to their partner, or the pair had a mutual video call (both were in the call, so both
  engaged);
* ``confirmed`` is set only once *both* partners are in ``confirmed_by``.

A one-way message is not evidence: it shows the sender turned up, not that the partner
ever saw the match. Those rows are reported as undecidable rather than guessed at.

The command never clears ``confirmed``. Some rows were set True by the old
"any message or call" shortcut and may not survive the stricter rule, but demoting them
would hide live matches from users, so they are only counted and left alone —
``--report-overconfirmed`` lists them.

Dry run by default; pass ``--apply`` to write.
"""

from chat.models import Message
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef

from management.models.matches import Match, MatchType


class Command(BaseCommand):
    help = "Backfill Match.confirmed / confirmed_by from mutual-contact evidence. Dry run unless --apply."

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
            "--report-overconfirmed",
            action="store_true",
            help="Also list matches flagged confirmed that show no mutual contact. Never modified.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]
        batch_size = options["batch_size"]
        report_overconfirmed = options["report_overconfirmed"]

        candidates = self._candidates()
        if limit:
            candidates = candidates[:limit]

        total = candidates.count() if limit is None else len(candidates)
        self.stdout.write(f"Examining {total} non-support, non-temporary matches.")

        stats = {
            "confirmed_by_added": 0,
            "matches_touched": 0,
            "confirmed_set": 0,
            "already_correct": 0,
            "undecidable": 0,
            "overconfirmed": 0,
        }
        undecidable_ids: list[int] = []
        overconfirmed_ids: list[int] = []

        for batch in self._batches(candidates, batch_size):
            with transaction.atomic():
                for match in batch:
                    self._process(match, stats, undecidable_ids, overconfirmed_ids, apply_changes)
                if not apply_changes:
                    transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Result" if apply_changes else "Dry run — nothing written"))
        self.stdout.write(f"  matches updated ..................... {stats['matches_touched']}")
        self.stdout.write(f"    confirmed_by rows added .......... {stats['confirmed_by_added']}")
        self.stdout.write(f"    confirmed flipped to True ........ {stats['confirmed_set']}")
        self.stdout.write(f"  already correct ..................... {stats['already_correct']}")
        self.stdout.write(f"  no mutual-contact evidence .......... {stats['undecidable']}")
        self.stdout.write(f"  flagged confirmed without evidence .. {stats['overconfirmed']} (left alone)")

        if report_overconfirmed and overconfirmed_ids:
            self.stdout.write("")
            self.stdout.write("Match IDs flagged confirmed with no mutual contact:")
            self.stdout.write(f"  {sorted(overconfirmed_ids)}")

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Re-run with --apply to write these changes."))

    # -- internals ---------------------------------------------------------

    def _candidates(self):
        """Matches whose confirmation state may be wrong, annotated with message evidence.

        Annotated rather than queried per row: the point of the command is to touch every
        match, and two `EXISTS` per row over ~3k matches is a needless N+1.
        """
        sent_by_user1 = Message.objects.filter(sender=OuterRef("user1"), recipient=OuterRef("user2"))
        sent_by_user2 = Message.objects.filter(sender=OuterRef("user2"), recipient=OuterRef("user1"))
        return (
            Match.objects.filter(support_matching=False)
            .exclude(match_type=MatchType.TEMPORARY)
            .annotate(_user1_messaged=Exists(sent_by_user1), _user2_messaged=Exists(sent_by_user2))
            .prefetch_related("confirmed_by")
            .order_by("id")
        )

    def _batches(self, queryset, batch_size):
        batch = []
        for match in queryset.iterator(chunk_size=batch_size):
            batch.append(match)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def _process(self, match, stats, undecidable_ids, overconfirmed_ids, apply_changes):
        mutual_call = match.total_mutal_video_calls_counter >= 1
        both_messaged = match._user1_messaged and match._user2_messaged
        has_evidence = mutual_call or both_messaged

        existing = {user.pk for user in match.confirmed_by.all()}
        complete = {match.user1_id, match.user2_id} <= existing

        if not has_evidence:
            if match.confirmed:
                stats["overconfirmed"] += 1
                overconfirmed_ids.append(match.pk)
            else:
                stats["undecidable"] += 1
                undecidable_ids.append(match.pk)
            return

        if complete and match.confirmed:
            stats["already_correct"] += 1
            return

        missing = {match.user1_id, match.user2_id} - existing
        if missing and apply_changes:
            match.confirmed_by.add(*missing)
        stats["confirmed_by_added"] += len(missing)

        if not match.confirmed:
            stats["confirmed_set"] += 1
            if apply_changes:
                match.confirmed = True
                match.save(update_fields=["confirmed", "updated_at"])

        stats["matches_touched"] += 1
