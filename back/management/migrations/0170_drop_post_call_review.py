"""Copy ``PostCallReview`` onto the post-call survey campaign, then drop the old table.

Duplicate ``(user, live_session)`` pairs collapse to the row with the greatest
``(updated_at, pk)``. Superseded rows are printed (and written to CSV when the filesystem
allows) before they are dropped.
"""

import csv
import os
from datetime import datetime, timezone

from django.conf import settings
from django.db import migrations

CAMPAIGN_SLUG = "post_call"
DISCARDED_EXPORT_COLUMNS = [
    "id",
    "user_id",
    "live_session_id",
    "rating",
    "review",
    "created_at",
    "updated_at",
]

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


def _export_discarded(rows) -> str:
    export_dir = os.environ.get("DJ_SURVEY_MIGRATION_EXPORT_DIR", str(settings.BASE_DIR))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    export_path = os.path.join(export_dir, f"discarded_post_call_reviews_{stamp}.csv")

    serialised = [
        {
            "id": row.pk,
            "user_id": row.user_id,
            "live_session_id": row.live_session_id,
            "rating": row.rating,
            "review": row.review,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }
        for row in rows
    ]

    try:
        with open(export_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=DISCARDED_EXPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(serialised)
        print(f"[surveys] exported {len(serialised)} discarded post-call reviews to {export_path}")
    except OSError as e:
        print(f"[surveys] could not write discarded-review export ({e}); relying on the printed copy")

    for row in serialised:
        print(f"[surveys] discarded post-call review: {row}")
    return export_path


def migrate_reviews(apps, schema_editor):
    PostCallReview = apps.get_model("management", "PostCallReview")
    SurveyCampaign = apps.get_model("management", "SurveyCampaign")
    SurveyResponse = apps.get_model("management", "SurveyResponse")

    campaign, _ = SurveyCampaign.objects.get_or_create(
        slug=CAMPAIGN_SLUG,
        defaults={
            "name": "Post-call feedback",
            "copy": CAMPAIGN_COPY,
            "scale": 5,
            "questions": POST_CALL_QUESTIONS,
            "audience_type": "all",
            "audience_value": "",
            "trigger": "event:call_ended",
            "eligible_after_event": "",
            "repeat_scope": "context",
            "context_type": "live_session",
            "active": True,
            "max_shows": 3,
        },
    )

    reviews = list(PostCallReview.objects.select_related("live_session").order_by("pk"))
    if not reviews:
        return

    orphaned = [review for review in reviews if review.user_id is None]
    if orphaned:
        print(f"[surveys] skipping {len(orphaned)} post-call review(s) with no user: {[r.pk for r in orphaned]}")

    groups: dict[tuple[int, int | None], list] = {}
    for review in reviews:
        if review.user_id is None:
            continue
        groups.setdefault((review.user_id, review.live_session_id), []).append(review)

    survivors, discarded = [], []
    for group in groups.values():
        ordered = sorted(group, key=lambda r: (r.updated_at, r.pk))
        survivors.append(ordered[-1])
        discarded.extend(ordered[:-1])

    if discarded:
        _export_discarded(discarded)

    responses = []
    for review in survivors:
        answers = {}
        if review.rating is not None:
            answers["rating"] = review.rating
        if review.review and review.review.strip():
            answers["comment"] = review.review.strip()
        responses.append(
            SurveyResponse(
                campaign=campaign,
                user_id=review.user_id,
                context_key=f"live_session:{review.live_session.uuid}" if review.live_session_id else "",
                live_session_id=review.live_session_id,
                answers=answers,
                rating=review.rating,
                status="submitted",
                shown_count=1,
                shown_at=review.created_at,
                submitted_at=review.created_at,
            )
        )

    created = SurveyResponse.objects.bulk_create(responses, batch_size=500)

    for response, review in zip(created, survivors):
        response.created_at = review.created_at
        response.updated_at = review.updated_at
    SurveyResponse.objects.bulk_update(created, ["created_at", "updated_at"], batch_size=500)

    migrated = SurveyResponse.objects.filter(campaign=campaign).count()
    if migrated != len(survivors):
        raise RuntimeError(f"[surveys] expected {len(survivors)} migrated responses, found {migrated}")
    print(
        f"[surveys] migrated {migrated} post-call reviews "
        f"({len(reviews)} rows in, {len(discarded)} superseded, {len(orphaned)} without a user)."
    )


def unmigrate_reviews(apps, schema_editor):
    SurveyCampaign = apps.get_model("management", "SurveyCampaign")
    SurveyResponse = apps.get_model("management", "SurveyResponse")

    SurveyResponse.objects.filter(campaign__slug=CAMPAIGN_SLUG).delete()
    SurveyCampaign.objects.filter(slug=CAMPAIGN_SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0169_survey_campaigns"),
    ]

    operations = [
        migrations.RunPython(migrate_reviews, unmigrate_reviews),
        migrations.DeleteModel(
            name="PostCallReview",
        ),
    ]
