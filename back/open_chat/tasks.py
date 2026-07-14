"""Celery task registration entrypoint for the open_chat app.

Importing the interaction modules here ensures the shared tasks are registered
when Celery autodiscovers ``open_chat.tasks``.
"""

from open_chat.basic_chat_interaction import open_chat_basic_chat_interaction  # noqa: F401
from open_chat.message_reply_suggestion import (  # noqa: F401
    idempotent_actions__generate_message_replies,
    open_chat_run_message_reply_suggestion_interaction,
)
