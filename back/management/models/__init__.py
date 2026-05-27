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
    courses,
    help_message,
    management_access_grant,
    management_tasks,
    matches,
    news_and_updates,
    newsletter,
    notifications,
    past_matches,
    pre_matching_appointment,
    profile,
    scores,
    settings,
    short_links,
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
    "banner",
    "community_events",
    "courses",
    "backend_state",
    "news_and_updates",
    "help_message",
    "past_matches",
    "translation_logs",
    "unconfirmed_matches",
    "matches",
    "management_tasks",
    "management_access_grant",
    "sms",
    "scores",
    "pre_matching_appointment",
    "newsletter",
    "stats",
    "short_links",
]
