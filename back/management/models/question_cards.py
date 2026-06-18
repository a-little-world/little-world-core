from uuid import uuid4

from django.db import models


def default_translation_content(en: str = "", de: str = "") -> dict[str, str]:
    return {"en": en, "de": de}


# Kept for historical migrations that reference this symbol.
_base_translations_dict = default_translation_content


class QuestionCardCategory(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    content = models.JSONField(default=default_translation_content)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "uuid"]

    def __str__(self) -> str:
        return self.content.get("en") or str(self.uuid)


class QuestionCard(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    category = models.ForeignKey(
        QuestionCardCategory,
        on_delete=models.CASCADE,
        related_name="cards",
    )
    content = models.JSONField(default=default_translation_content)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "uuid"]

    def __str__(self) -> str:
        return self.content.get("en") or str(self.uuid)


class UserQuestionCardPreference(models.Model):
    """Per-user question card preferences (archive, favourite, etc.)."""

    class Kind(models.TextChoices):
        ARCHIVED = "archived", "Archived"
        FAVOURITED = "favourited", "Favourited"

    user = models.ForeignKey(
        "management.User",
        on_delete=models.CASCADE,
        related_name="question_card_preferences",
    )
    card = models.ForeignKey(
        QuestionCard,
        on_delete=models.CASCADE,
        related_name="user_preferences",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "card", "kind"],
                name="unique_user_question_card_preference",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.kind} {self.card_id}"
