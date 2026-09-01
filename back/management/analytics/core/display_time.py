"""Display timezone and date-bound helpers for analytics date filters.

One display timezone per package (conventions §10). Date-only bounds are interpreted in
this timezone rather than the project default, so a row displayed as "1 Jan" is included
by ``from=2026-01-01``. ``video/analytics/display_time.py`` is the sibling for that
package; the behaviour must match even though the code is not shared.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.utils import timezone

DISPLAY_TIMEZONE = ZoneInfo("Europe/Berlin")


def now() -> datetime:
    """Current instant, for ``as_of`` defaults."""
    return timezone.now()


def today() -> date:
    """Current calendar date in the display timezone, not the server's."""
    return timezone.now().astimezone(DISPLAY_TIMEZONE).date()


def start_of_day(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=DISPLAY_TIMEZONE)


def end_of_day_inclusive(d: date) -> datetime:
    return datetime.combine(d, time.max, tzinfo=DISPLAY_TIMEZONE)


def as_display_date(value: date | datetime | str) -> date:
    """Coerce a bound to a calendar date in the display timezone.

    An aware datetime is converted before its date is taken, so an instant that is still
    "yesterday" in Berlin is not read as today.
    """
    if isinstance(value, str):
        return date.fromisoformat(value)
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            return value.astimezone(DISPLAY_TIMEZONE).date()
        return value.date()
    return value


def parse_date_start(start: date | datetime | str) -> date:
    return as_display_date(start)


def parse_start_bound(start: date | datetime | str) -> datetime:
    """Inclusive start-of-day in the display timezone."""
    return start_of_day(as_display_date(start))


def parse_end_bound(end: date | datetime | str) -> datetime:
    """Inclusive end-of-day in the display timezone.

    A naive datetime is coerced to the display timezone rather than passed through —
    passing it through means ``"2026-01-01"`` and ``datetime(2026, 1, 1)`` resolve to
    different instants, one of them in the project default timezone.
    """
    if isinstance(end, datetime):
        if timezone.is_naive(end):
            return end.replace(tzinfo=DISPLAY_TIMEZONE)
        return end
    if isinstance(end, str):
        end = date.fromisoformat(end)
    return end_of_day_inclusive(end)


def inclusive_range(start: date | datetime | str, end: date | datetime | str) -> tuple[datetime, datetime]:
    """Both bounds of a closed date range, in the display timezone."""
    return parse_start_bound(start), parse_end_bound(end)
