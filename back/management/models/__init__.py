"""
Main management models:
- Profile: all info that is provided in the user_form
- User (default django model): The user email + password and some metadata
- State (user): A user state
- Settings (user): All user settings
"""

from . import (
    backend_state,
    banner,
    community_events,
    help_message,
    management_tasks,
    matches,
    news_and_updates,
    newsletter,
    notifications,
    past_matches,
    pre_matching_appointment,
    profile,
    rooms,
    scores,
    settings,
    sms,
    state,
    stats,
    translation_logs,
    unconfirmed_matches,
    user,
)

__all__ = [
    "profile",
    "user",
    "state",
    "settings",
    "notifications",
    "rooms",
    "banner",
    "community_events",
    "backend_state",
    "news_and_updates",
    "help_message",
    "past_matches",
    "translation_logs",
    "unconfirmed_matches",
    "matches",
    "management_tasks",
    "sms",
    "scores",
    "pre_matching_appointment",
    "newsletter",
    "stats",
]
