"""
Backward compatibility for historical migrations.

Old migrations import ``management.models.question_deck``; new code should use
``management.models.question_cards`` instead.
"""

from management.models.question_cards import *  # noqa: F403
from management.models.question_cards import default_translation_content

# Symbols referenced by migrations 0054 and 0056.
_base_translations_dict = default_translation_content


def _default_cards():
    return []
