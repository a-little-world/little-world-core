"""Occurrence queries used by the time-series metric catalog."""

from collections import defaultdict
from datetime import date, timedelta

from chat.models import Message
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db.models import Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from emails.models import EmailLog
from video.models import LivekitSession

from management.analytics.core.display_time import DISPLAY_TIMEZONE, inclusive_range
from management.analytics.core.time_series import BucketAggregate
from management.analytics.registry import get_catalog_entry
from management.permissions import ManagementPermission


def _trunc(field_name: str, bucket_size: int):
    truncators = {1: TruncDay, 7: TruncWeek, 30: TruncMonth}
    try:
        return truncators[bucket_size](field_name, tzinfo=DISPLAY_TIMEZONE)
    except KeyError as exc:
        raise ValueError("bucket_size must be one of 1, 7, or 30") from exc


def _bucket_date(value) -> date:
    if hasattr(value, "astimezone"):
        return value.astimezone(DISPLAY_TIMEZONE).date()
    return value


def _count_rows(queryset, field_name: str, bucket_size: int) -> dict[date, BucketAggregate]:
    rows = (
        queryset.annotate(bucket=_trunc(field_name, bucket_size))
        .values("bucket")
        .annotate(value=Count("pk"))
        .order_by("bucket")
    )
    return {_bucket_date(row["bucket"]): BucketAggregate(total=row["value"], count=row["value"]) for row in rows}


def user_signups(users, *, start_date, end_date, bucket_size, **_kwargs):
    start, end = inclusive_range(start_date, end_date)
    baseline = get_catalog_entry("funnel__all").build(users)
    return _count_rows(baseline.filter(date_joined__range=(start, end)), "date_joined", bucket_size)


def emails_sent(users, *, start_date, end_date, bucket_size, dynamic_only=False, **_kwargs):
    start, end = inclusive_range(start_date, end_date)
    queryset = EmailLog.objects.filter(
        receiver__in=users,
        time__range=(start, end),
        sucess=True,
    )
    if dynamic_only:
        queryset = queryset.filter(is_dyanmic_email=True)
    return _count_rows(queryset, "time", bucket_size)


def dynamic_emails_sent(users, **kwargs):
    return emails_sent(users, dynamic_only=True, **kwargs)


def user_sessions(users, *, start_date, end_date, bucket_size, **_kwargs):
    """Count authenticated sessions by their estimated creation time.

    Django's session table has no creation timestamp or user foreign key. Decode only
    rows in the requested date range, then apply the accessible-user cohort.

    The estimate holds only while nothing re-saves a session after login (which would
    move ``expire_date``), ``clearsessions`` is not scheduled (which would delete past
    rows) and ``SESSION_COOKIE_AGE`` is unchanged (which would shift every date).
    """
    start, end = inclusive_range(start_date, end_date)
    session_duration = timedelta(seconds=getattr(settings, "SESSION_COOKIE_AGE", 1209600))
    accessible_ids = {str(user_id) for user_id in users.values_list("id", flat=True)}
    aggregates: dict[date, int] = defaultdict(int)

    sessions = Session.objects.filter(expire_date__range=(start + session_duration, end + session_duration)).only(
        "session_data", "expire_date"
    )
    for session in sessions:
        if str(session.get_decoded().get("_auth_user_id")) not in accessible_ids:
            continue
        created_at = session.expire_date - session_duration
        local_date = created_at.astimezone(DISPLAY_TIMEZONE).date()
        if bucket_size == 7:
            local_date -= timedelta(days=local_date.weekday())
        elif bucket_size == 30:
            local_date = local_date.replace(day=1)
        aggregates[local_date] += 1

    return {bucket: BucketAggregate(total=count, count=count) for bucket, count in aggregates.items()}


def user_messages(users, *, start_date, end_date, bucket_size, **_kwargs):
    start, end = inclusive_range(start_date, end_date)
    support_user = (
        Q(sender__is_staff=True)
        | Q(recipient__is_staff=True)
        | Q(sender__user_permissions__codename=ManagementPermission.MATCHING_USER.codename)
        | Q(recipient__user_permissions__codename=ManagementPermission.MATCHING_USER.codename)
        | Q(sender__groups__permissions__codename=ManagementPermission.MATCHING_USER.codename)
        | Q(recipient__groups__permissions__codename=ManagementPermission.MATCHING_USER.codename)
    )
    queryset = (
        Message.objects.filter(
            sender__in=users,
            recipient__in=users,
            created__range=(start, end),
        )
        .exclude(support_user)
        .distinct()
    )
    return _count_rows(queryset, "created", bucket_size)


def _call_queryset(users, *, start_date, end_date, call_type):
    """Completed calls in which both participants were active.

    Unfinished calls are excluded from every call metric, not just durations, so call
    counts and duration totals always describe the same calls.
    """
    start, end = inclusive_range(start_date, end_date)
    queryset = LivekitSession.objects.filter(
        u1__in=users,
        u2__in=users,
        both_have_been_active=True,
        end_time__isnull=False,
        created_at__range=(start, end),
    )
    if call_type == "standard":
        queryset = queryset.filter(random_call_session=False)
    elif call_type == "random":
        queryset = queryset.filter(random_call_session=True)
    return queryset


def video_call_count(users, *, start_date, end_date, bucket_size, call_type, **_kwargs):
    queryset = _call_queryset(
        users,
        start_date=start_date,
        end_date=end_date,
        call_type=call_type,
    )
    return _count_rows(queryset, "created_at", bucket_size)


def video_call_duration(users, *, start_date, end_date, bucket_size, call_type, **_kwargs):
    duration = ExpressionWrapper(F("end_time") - F("created_at"), output_field=DurationField())
    rows = (
        _call_queryset(
            users,
            start_date=start_date,
            end_date=end_date,
            call_type=call_type,
        )
        .annotate(bucket=_trunc("created_at", bucket_size))
        .values("bucket")
        .annotate(total_duration=Sum(duration), call_count=Count("pk"))
        .order_by("bucket")
    )
    return {
        _bucket_date(row["bucket"]): BucketAggregate(
            total=row["total_duration"].total_seconds(),
            count=row["call_count"],
        )
        for row in rows
        if row["total_duration"] is not None
    }
