import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import management.models.question_cards


class Migration(migrations.Migration):

    dependencies = [
        ("management", "0158_course_coursechapter_chapterquizstep_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="state",
            name="question_card_deck",
        ),
        migrations.DeleteModel(
            name="QuestionCardsDeck",
        ),
        migrations.DeleteModel(
            name="QuestionCard",
        ),
        migrations.DeleteModel(
            name="QuestionCardCategories",
        ),
        migrations.CreateModel(
            name="QuestionCardCategory",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "content",
                    models.JSONField(default=management.models.question_cards.default_translation_content),
                ),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "ordering": ["sort_order", "uuid"],
            },
        ),
        migrations.CreateModel(
            name="QuestionCard",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "content",
                    models.JSONField(default=management.models.question_cards.default_translation_content),
                ),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cards",
                        to="management.questioncardcategory",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "uuid"],
            },
        ),
        migrations.CreateModel(
            name="UserQuestionCardPreference",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("archived", "Archived"),
                            ("favourited", "Favourited"),
                        ],
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "card",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_preferences",
                        to="management.questioncard",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="question_card_preferences",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="userquestioncardpreference",
            constraint=models.UniqueConstraint(
                fields=("user", "card", "kind"),
                name="unique_user_question_card_preference",
            ),
        ),
    ]
