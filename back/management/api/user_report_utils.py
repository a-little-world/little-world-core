from chat.models import Message
from django.db.models import Q
from translations import get_translation
from video.models import LivekitSession

from management.models.matches import Match
from management.models.unconfirmed_matches import ProposedMatch


def seconds_to_hhmm(total_seconds):
    total_minutes = int(round(float(total_seconds) / 60.0))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def datetime_to_readable_utc(value):
    if not value:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


def get_german_language_level(user):
    lang_skill = (user.profile.lang_skill if user.profile else None) or []
    german_entry = next((entry for entry in lang_skill if entry.get("lang") == "german"), None)
    level_code = german_entry.get("level") if german_entry else None
    if not level_code:
        return None

    level_to_translation_key = {
        "level-0": "profile.lang_level.level_0",
        "level-1": "profile.lang_level.level_1",
        "level-2": "profile.lang_level.level_2",
        "level-3": "profile.lang_level.level_3",
        "level-4": "profile.lang_level.level_4_native.vol",
    }
    translation_key = level_to_translation_key.get(level_code)
    return get_translation(translation_key, lang="en") if translation_key else level_code


def group_user_journey_by_date(user_path):
    from collections import defaultdict

    if not user_path:
        return []

    buckets_by_date = defaultdict(set)
    for bucket_id, timestamp in user_path:
        if isinstance(timestamp, str):
            date_str = timestamp.split(" ")[0]
        else:
            date_str = str(timestamp.date())
        buckets_by_date[date_str].add(bucket_id)

    sorted_dates = sorted(buckets_by_date.keys())
    if not sorted_dates:
        return []

    result = []
    current_start = sorted_dates[0]
    current_end = sorted_dates[0]
    current_buckets = frozenset(buckets_by_date[sorted_dates[0]])

    for date_str in sorted_dates[1:]:
        date_buckets = frozenset(buckets_by_date[date_str])

        if date_buckets == current_buckets:
            current_end = date_str
        else:
            result.append(
                {
                    "start_date": current_start,
                    "end_date": current_end if current_end != current_start else None,
                    "buckets": sorted(list(current_buckets)),
                }
            )
            current_start = date_str
            current_end = date_str
            current_buckets = date_buckets

    result.append(
        {
            "start_date": current_start,
            "end_date": current_end if current_end != current_start else None,
            "buckets": sorted(list(current_buckets)),
        }
    )

    return result


def build_user_report_entry(user):
    all_matches = Match.objects.filter(
        (Q(user1=user) | Q(user2=user)),
        support_matching=False,
    ).order_by("-created_at")

    total_matches = all_matches.count()
    active_matches = all_matches.filter(active=True).count()

    match_status = []
    if active_matches > 0:
        match_status.append("Active")
    if all_matches.filter(confirmed=True).exists():
        match_status.append("Confirmed")
    if all_matches.filter(completed=True).exists():
        match_status.append("Completed")
    if not match_status:
        match_status = ["No matches"]

    match_details = []
    for match in all_matches:
        status = "Confirmed" if match.confirmed else "Pending Confirmation"
        other_username = match.user2.username if match.user1 == user else match.user1.username
        confirmation_parts = []
        if match.confirmed_by == match.user1:
            confirmation_parts.append(f"{match.user1.username} confirmed")
        elif match.confirmed_by == match.user2:
            confirmation_parts.append(f"{match.user2.username} confirmed")
        else:
            confirmation_parts.append("Both confirmed" if match.confirmed else "No one confirmed")
        match_details.append(
            {
                "other_username": other_username,
                "status": status,
                "confirmation": ", ".join(confirmation_parts),
            }
        )

    video_calls_as_u1 = LivekitSession.objects.filter(u1=user, both_have_been_active=True)
    video_calls_as_u2 = LivekitSession.objects.filter(u2=user, both_have_been_active=True)
    video_calls = video_calls_as_u1.union(video_calls_as_u2)

    total_video_calls = video_calls.count()
    total_video_time_seconds_user = 0
    video_call_details = []

    for call in video_calls:
        other_user = call.u1 if call.u1 != user else call.u2
        active_status = "Active" if call.is_active else "Inactive"

        if call.end_time:
            duration = call.end_time - call.created_at
            total_video_time_seconds_user += duration.total_seconds()
            video_call_details.append(
                {
                    "other_username": other_user.username,
                    "duration_seconds": duration.total_seconds(),
                    "status": active_status,
                }
            )
        else:
            video_call_details.append({"other_username": other_user.username, "status": active_status})

    most_recent_match = all_matches.first()
    video_calls_with_recent_match = 0
    messages_with_recent_match = 0

    if most_recent_match:
        other_user = most_recent_match.user2 if most_recent_match.user1 == user else most_recent_match.user1
        video_calls_with_recent_match = LivekitSession.objects.filter(
            (Q(u1=user, u2=other_user) | Q(u1=other_user, u2=user)),
            both_have_been_active=True,
        ).count()
        messages_with_recent_match = Message.objects.filter(
            Q(sender=user, recipient=other_user) | Q(sender=other_user, recipient=user)
        ).count()

    last_message = Message.objects.filter(recipient=user).order_by("-created").first()
    messages_sent = Message.objects.filter(sender=user).count()
    messages_received = Message.objects.filter(recipient=user).count()

    raw_path = user.state.user_journey_path or []
    grouped_journey = group_user_journey_by_date(raw_path)

    total_video_time_minutes = round(total_video_time_seconds_user / 60, 2)
    total_video_time_hhmm = seconds_to_hhmm(total_video_time_seconds_user)
    expired_proposals_count = (
        ProposedMatch.objects.filter(
            Q(user1=user) | Q(user2=user),
            expired=True,
            closed=True,
        )
        .exclude(match_type="temporary")
        .count()
    )
    german_language_level = get_german_language_level(user)

    return {
        "user_id": user.id,
        "vorname": user.profile.first_name if user.profile else "",
        "nachname": user.profile.second_name if user.profile else "",
        "email": user.email,
        "date_joined": (user.date_joined.isoformat() if user.date_joined else None),
        "last_login": (user.last_login.isoformat() if user.last_login else None),
        "german_language_level": german_language_level,
        "user_type": (user.profile.user_type if user.profile else None),
        "expired_proposals_count": expired_proposals_count,
        "user_journey_path": grouped_journey,
        "match_status": ", ".join(match_status),
        "total_matches": total_matches,
        "active_matches": active_matches,
        "match_details": match_details,
        "video_call_details": video_call_details,
        "total_video_calls": total_video_calls,
        "total_video_time_minutes": total_video_time_minutes,
        "total_video_time_hhmm": total_video_time_hhmm,
        "messages_sent": messages_sent,
        "messages_received": messages_received,
        "video_calls_with_most_recent_match": video_calls_with_recent_match,
        "messages_with_most_recent_match": messages_with_recent_match,
        "last_message_received": datetime_to_readable_utc(last_message.created if last_message else None),
    }
