from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

# Single source for display "day" / calendar date in admin analytics (ops timezone).
DISPLAY_TZ = ZoneInfo("Europe/Berlin")


def parse_analytics_datetime_bound(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    """Parse a filter bound for analytics list queries.

    Date-only values are interpreted in DISPLAY_TZ (Europe/Berlin) so date filters
    align with the day/date columns shown in the admin UI.
    """
    if not value:
        return None
    parsed_dt = parse_datetime(value)
    if parsed_dt is not None:
        if timezone.is_naive(parsed_dt):
            return parsed_dt.replace(tzinfo=DISPLAY_TZ)
        return parsed_dt
    parsed_date = parse_date(value)
    if parsed_date is None:
        return None
    bound_time = time.max if end_of_day else time.min
    return datetime.combine(parsed_date, bound_time, tzinfo=DISPLAY_TZ)
