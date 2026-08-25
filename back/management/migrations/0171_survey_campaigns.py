"""Survey campaigns, response GIN index, and the banner/event filter choices without Capgemini.

Capgemini rows were already cleared on production, so this only updates the choice list.
"""

import django.core.validators
import django.db.models.deletion
import management.models.survey
from django.conf import settings
from django.db import migrations, models

FILTER_CHOICES = [
    ("learners_with_a1a2", "learners_with_a1a2"),
    ("learners_above_a1a2", "learners_above_a1a2"),
    ("volunteers", "volunteers"),
    ("learners", "learners"),
    ("learners_outside_germany", "learners_outside_germany"),
    ("random_call_users", "random_call_users"),
    ("match_eligible_users", "match_eligible_users"),
    ("nrw_residents", "nrw_residents"),
    ("none", "None"),
]

GIN_INDEX = "survey_response_answers_gin"


def create_answers_gin(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f'CREATE INDEX IF NOT EXISTS {GIN_INDEX} ON management_surveyresponse USING gin ("answers")')


def drop_answers_gin(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP INDEX IF EXISTS {GIN_INDEX}")


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0170_mobile_device_session_active_at"),
        ("video", "0028_randomcallmatching_u1_status_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SurveyCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "slug",
                    models.SlugField(
                        help_text="Stable URL-safe identifier using hyphens, e.g. 'post-call'. Referenced by code and analytics.",
                        max_length=64,
                        unique=True,
                    ),
                ),
                ("name", models.CharField(help_text="Internal name for the campaign", max_length=255)),
                (
                    "copy",
                    models.JSONField(
                        default=management.models.survey.default_campaign_copy,
                        help_text=(
                            "User-facing card copy per language: title, description and submit_button. "
                            "German is required to go live; English falls back to it. Star captions live in "
                            "the frontend locales — they belong to the rating widget, not the campaign."
                        ),
                    ),
                ),
                (
                    "scale",
                    models.PositiveSmallIntegerField(
                        default=5,
                        help_text=(
                            "Number of stars (2–10). Frozen once a rating has been submitted: growing or shrinking "
                            "would change what existing scores mean."
                        ),
                        validators=[
                            django.core.validators.MinValueValidator(2),
                            django.core.validators.MaxValueValidator(10),
                        ],
                    ),
                ),
                (
                    "questions",
                    models.JSONField(
                        default=list,
                        help_text=(
                            "Ordered list of {id, type, required, label, placeholder?, options?}. Ids and types "
                            "are immutable once answered; labels can always be edited."
                        ),
                    ),
                ),
                (
                    "audience_type",
                    models.CharField(
                        choices=[
                            ("all", "All users"),
                            ("company", "Company"),
                            ("filter", "Existing audience filter"),
                        ],
                        default="all",
                        max_length=32,
                    ),
                ),
                (
                    "audience_value",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Company name when audience_type is 'company', or a CustomFilterChoices value when "
                            "it is 'filter'. Empty for everyone."
                        ),
                        max_length=255,
                    ),
                ),
                (
                    "trigger",
                    models.CharField(
                        choices=[
                            ("on_session", "Next time the user is in the app"),
                            ("event:call_ended", "After a qualifying call (excludes random calls)"),
                        ],
                        default="on_session",
                        max_length=32,
                    ),
                ),
                (
                    "eligible_after_event",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "Immediately"),
                            ("onboarded", "Onboarded"),
                            ("first_qualifying_call", "First qualifying call (excludes random calls)"),
                            ("match_created", "Match created"),
                            ("match_success", "Match success"),
                        ],
                        default="",
                        help_text=(
                            "Named journey condition. Takes effect as soon as the person matches it. "
                            "Match conditions count if any of the user's matches qualify; once-per-user "
                            "campaigns still offer the survey only once. Timing is controlled with "
                            "eligible_after_since."
                        ),
                        max_length=32,
                    ),
                ),
                (
                    "eligible_after_since",
                    models.DateTimeField(
                        blank=True,
                        help_text=(
                            "Lower bound on when eligible_after_event counts. Only people who reached that "
                            "condition on or after this instant are eligible. Empty means any time. Ignored "
                            "when the event is empty."
                        ),
                        null=True,
                    ),
                ),
                (
                    "repeat_scope",
                    models.CharField(
                        choices=[("user", "Once per user"), ("context", "Once per context")],
                        default="user",
                        max_length=16,
                    ),
                ),
                (
                    "context_type",
                    models.CharField(
                        blank=True,
                        choices=[("live_session", "Live session"), ("match", "Match")],
                        default="",
                        help_text="Required when repeat_scope is 'context'.",
                        max_length=32,
                    ),
                ),
                ("active", models.BooleanField(default=False)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                (
                    "max_shows",
                    models.PositiveSmallIntegerField(
                        default=3,
                        help_text="How many times an unanswered offer may be presented before it expires.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Survey campaign",
                "verbose_name_plural": "Survey campaigns",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SurveyResponse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "context_key",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="'' for user-scoped surveys, else '<context_type>:<uuid>'.",
                        max_length=128,
                    ),
                ),
                ("answers", models.JSONField(default=dict, help_text="Complete answer record, keyed by question id.")),
                (
                    "rating",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text="Mirror of the first rating answer, so aggregates read a column not JSON.",
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(10),
                        ],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("shown", "Shown"),
                            ("submitted", "Submitted"),
                            ("dismissed", "Dismissed"),
                            ("expired", "Expired"),
                        ],
                        default="shown",
                        max_length=16,
                    ),
                ),
                (
                    "shown_count",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text="Times the client confirmed it displayed the card. Flat at 0 means delivery is broken.",
                    ),
                ),
                ("shown_at", models.DateTimeField(blank=True, null=True)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        help_text="Retire campaigns with active=False; deleting one would orphan its answers.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="responses",
                        to="management.surveycampaign",
                    ),
                ),
                (
                    "live_session",
                    models.ForeignKey(
                        blank=True,
                        help_text="Set for live-session contexts; kept for referential integrity and analytics joins.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="survey_responses",
                        to="video.livekitsession",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="survey_responses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Survey response",
                "verbose_name_plural": "Survey responses",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["campaign", "status"], name="survey_response_campaign_idx"),
                    models.Index(fields=["user", "status"], name="survey_response_user_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("campaign", "user", "context_key"),
                        name="unique_survey_response_per_context",
                    )
                ],
            },
        ),
        migrations.RunPython(create_answers_gin, drop_answers_gin),
        migrations.AlterField(
            model_name="banner",
            name="custom_filter",
            field=models.CharField(choices=FILTER_CHOICES, default="none", max_length=255),
        ),
        migrations.AlterField(
            model_name="communityevent",
            name="custom_filter",
            field=models.CharField(choices=FILTER_CHOICES, default="none", max_length=255),
        ),
    ]
