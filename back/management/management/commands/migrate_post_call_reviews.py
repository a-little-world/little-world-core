"""Copy ``PostCallReview`` rows onto the post-call ``SurveyCampaign``.

This was a data migration. It is a command instead so the copy can be run, checked and — if
necessary — re-run *before* anything drops the source table. ``0173`` creates the survey
tables; a later migration drops ``PostCallReview`` once the numbers here look right.

Duplicates
----------
The old table has no uniqueness rule, so one ``(user, live_session)`` pair can hold several
rows. ``SurveyResponse`` is unique on ``(campaign, user, context_key)``, so each group
collapses to the row with the greatest ``(updated_at, pk)`` — the most recent edit wins.
Superseded rows are written to a CSV before they are dropped.

That CSV holds user free text, so it goes to a temporary directory rather than anywhere
inside the source tree, and the text is never logged — the printed line names ids only. Set
``DJ_SURVEY_MIGRATION_EXPORT_DIR`` to collect it somewhere durable.

Rows with no ``live_session`` are skipped: the campaign is context-scoped on the live
session, so there is no context to key them on. They are listed in the export too, so
nothing disappears silently.

Re-running is safe. Responses are matched on ``(campaign, user, context_key)`` and existing
ones are left exactly as they are, so a partial run can simply be repeated. That also covers
the gap between deploying ``0173`` and running this: a real post-call survey answered in
between is never overwritten.

Dry run by default; pass ``--apply`` to write.
"""

import csv
import os
import tempfile
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from management.models.post_call_review import PostCallReview
from management.models.survey import SurveyCampaign, SurveyResponse

CAMPAIGN_SLUG = "post-call"

DISCARDED_EXPORT_COLUMNS = ["id", "user_id", "live_session_id", "rating", "review", "created_at", "updated_at", "why"]

CAMPAIGN_COPY = {
    "title": {
        "de": "Bewertet die Qualität Ihres Anrufs",
        "en": "Rate the quality of your call",
    },
    "description": {
        "de": (
            "Wir würden uns sehr über dein Feedback freuen, damit wir die Qualität unserer "
            "Anrufe auf hohem Niveau halten können."
        ),
        "en": "We'd greatly appreciate your feedback so we can keep the quality of our calls high.",
    },
    "submit_button": {"de": "Feedback abgeben", "en": "Submit feedback"},
}

POST_CALL_QUESTIONS = [
    {
        "id": "rating",
        "type": "rating",
        "required": True,
        "label": {"de": "Anrufqualität", "en": "Call quality"},
    },
    {
        "id": "comment",
        "type": "text",
        "required": False,
        "label": {"de": "Hinterlasse einen Kommentar", "en": "Additional comments"},
        "placeholder": {"de": "Schreib dein Feedback hier", "en": "Leave your feedback here"},
    },
]


class Command(BaseCommand):
    help = "Copy PostCallReview rows onto the post-call survey campaign. Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the changes. Without this the command only reports what it would do.",
        )
        parser.add_argument(
            "--activate-campaign",
            action="store_true",
            help=(
                "Create the campaign with active=True. Off by default: an active campaign starts "
                "offering the survey immediately, which is only wanted once the client that renders "
                "it is deployed. Switch it on in the admin panel instead."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        stats = {"read": 0, "written": 0, "already_present": 0, "superseded": 0, "no_live_session": 0, "no_user": 0}
        discarded = []

        with transaction.atomic():
            campaign = self._campaign(active=options["activate_campaign"])
            survivors = self._survivors(stats, discarded)
            self._write(campaign, survivors, stats)
            if not apply_changes:
                transaction.set_rollback(True)

        if discarded:
            self._export(discarded)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Result" if apply_changes else "Dry run — nothing written"))
        self.stdout.write(f"  reviews read ........................ {stats['read']}")
        self.stdout.write(f"  responses created ................... {stats['written']}")
        self.stdout.write(f"  already migrated (left alone) ....... {stats['already_present']}")
        self.stdout.write(f"  superseded duplicates dropped ....... {stats['superseded']}")
        self.stdout.write(f"  skipped — no live session ........... {stats['no_live_session']}")
        self.stdout.write(f"  skipped — no user ................... {stats['no_user']}")

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Re-run with --apply to write these changes."))

    # -- internals ---------------------------------------------------------

    def _campaign(self, *, active: bool) -> SurveyCampaign:
        """The post-call campaign, created through the real model so it is validated.

        ``SurveyCampaign.save()`` runs ``full_clean()``, so the copy completeness, question
        schema and scope rules all apply here — none of which a historical model in a data
        migration would have checked.
        """
        campaign = SurveyCampaign.objects.filter(slug=CAMPAIGN_SLUG).first()
        if campaign is not None:
            self.stdout.write(f"Using existing campaign '{CAMPAIGN_SLUG}' (id={campaign.pk}).")
            return campaign

        campaign = SurveyCampaign(
            slug=CAMPAIGN_SLUG,
            name="Post-call feedback",
            copy=CAMPAIGN_COPY,
            scale=5,
            questions=POST_CALL_QUESTIONS,
            audience_type=SurveyCampaign.AudienceType.ALL,
            audience_value="",
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            eligible_after_event="",
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
            active=active,
            max_shows=3,
        )
        campaign.save()
        state = "active" if active else "inactive — switch it on in the admin panel when the client is live"
        self.stdout.write(f"Created campaign '{CAMPAIGN_SLUG}' ({state}).")
        return campaign

    def _survivors(self, stats, discarded):
        """One review per ``(user, live_session)``: the most recently edited."""
        reviews = list(PostCallReview.objects.select_related("live_session").order_by("pk"))
        stats["read"] = len(reviews)

        groups: dict[tuple[int, int], list] = {}
        for review in reviews:
            if review.user_id is None:
                stats["no_user"] += 1
                discarded.append((review, "no user"))
                continue
            if review.live_session_id is None:
                stats["no_live_session"] += 1
                discarded.append((review, "no live session"))
                continue
            groups.setdefault((review.user_id, review.live_session_id), []).append(review)

        survivors = []
        for group in groups.values():
            ordered = sorted(group, key=lambda r: (r.updated_at, r.pk))
            survivors.append(ordered[-1])
            for superseded in ordered[:-1]:
                stats["superseded"] += 1
                discarded.append((superseded, "superseded duplicate"))
        return survivors

    def _write(self, campaign, survivors, stats):
        existing = set(SurveyResponse.objects.filter(campaign=campaign).values_list("user_id", "context_key"))

        to_create = []
        sources = []
        for review in survivors:
            context_key = f"live_session:{review.live_session.uuid}"
            if (review.user_id, context_key) in existing:
                stats["already_present"] += 1
                continue

            answers = {}
            if review.rating is not None:
                answers["rating"] = review.rating
            if review.review and review.review.strip():
                answers["comment"] = review.review.strip()

            sources.append(review)
            to_create.append(
                SurveyResponse(
                    campaign=campaign,
                    user_id=review.user_id,
                    context_key=context_key,
                    live_session_id=review.live_session_id,
                    answers=answers,
                    rating=review.rating,
                    status=SurveyResponse.Status.SUBMITTED,
                    shown_count=1,
                    shown_at=review.created_at,
                    submitted_at=review.created_at,
                )
            )

        if not to_create:
            return

        created = SurveyResponse.objects.bulk_create(to_create, batch_size=500)
        stats["written"] = len(created)

        # `bulk_create` stamps `created_at` from auto_now_add; this puts the original times
        # back. `bulk_update` writes attributes directly without calling `pre_save`, so
        # `auto_now` on `updated_at` does not overwrite them again.
        for response, review in zip(created, sources, strict=True):
            response.created_at = review.created_at
            response.updated_at = review.updated_at
        SurveyResponse.objects.bulk_update(created, ["created_at", "updated_at"], batch_size=500)

    def _export(self, discarded):
        export_dir = os.environ.get("DJ_SURVEY_MIGRATION_EXPORT_DIR") or tempfile.gettempdir()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        path = os.path.join(export_dir, f"discarded_post_call_reviews_{stamp}.csv")

        rows = [
            {
                "id": review.pk,
                "user_id": review.user_id,
                "live_session_id": review.live_session_id,
                "rating": review.rating,
                "review": review.review,
                "created_at": review.created_at.isoformat() if review.created_at else "",
                "updated_at": review.updated_at.isoformat() if review.updated_at else "",
                "why": why,
            }
            for review, why in discarded
        ]

        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=DISCARDED_EXPORT_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(f"Exported {len(rows)} dropped review(s) to {path}")
        except OSError as e:
            self.stdout.write(self.style.WARNING(f"Could not write the export ({e})"))

        # Ids only: the review text is the reason the export is not left in the repo, so it
        # has no business in a deploy log either.
        self.stdout.write(f"Dropped review ids: {[row['id'] for row in rows]}")
