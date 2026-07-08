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


def get_latest_support_chat_messages(user):
    support_matches = Match.objects.filter(
        Q(user1=user) | Q(user2=user),
        active=True,
        support_matching=True,
    ).values_list("user1_id", "user2_id")
    support_partner_ids = [user2_id if user1_id == user.id else user1_id for user1_id, user2_id in support_matches]

    if not support_partner_ids:
        return None, None

    last_user_to_support_message = (
        Message.objects.filter(sender=user, recipient_id__in=support_partner_ids).order_by("-created").first()
    )
    last_support_to_user_reply = (
        Message.objects.filter(sender_id__in=support_partner_ids, recipient=user).order_by("-created").first()
    )

    return last_user_to_support_message, last_support_to_user_reply


def build_user_report_entry(user, selected_fields=None):
    selected_field_set = set(selected_fields) if selected_fields else None

    def include(field_name):
        return selected_field_set is None or field_name in selected_field_set

    result = {}

    if include("user_id"):
        result["user_id"] = user.id
    if include("vorname"):
        result["vorname"] = user.profile.first_name if user.profile else ""
    if include("nachname"):
        result["nachname"] = user.profile.second_name if user.profile else ""
    if include("email"):
        result["email"] = user.email
    if include("date_joined"):
        result["date_joined"] = user.date_joined.isoformat() if user.date_joined else None
    if include("last_login"):
        result["last_login"] = user.last_login.isoformat() if user.last_login else None
    if include("user_type"):
        result["user_type"] = user.profile.user_type if user.profile else None
    if include("german_language_level"):
        result["german_language_level"] = get_german_language_level(user)

    if include("user_journey_path"):
        raw_path = user.state.user_journey_path or []
        result["user_journey_path"] = group_user_journey_by_date(raw_path)

    if include("expired_proposals_count"):
        result["expired_proposals_count"] = (
            ProposedMatch.objects.filter(
                Q(user1=user) | Q(user2=user),
                expired=True,
                closed=True,
            )
            .exclude(match_type="temporary")
            .count()
        )

    all_matches = None

    def get_all_matches():
        nonlocal all_matches
        if all_matches is None:
            all_matches = Match.objects.filter(
                (Q(user1=user) | Q(user2=user)),
                support_matching=False,
            ).order_by("-created_at")
        return all_matches

    if include("total_matches"):
        result["total_matches"] = get_all_matches().count()

    if include("active_matches"):
        result["active_matches"] = get_all_matches().filter(active=True).count()

    if include("match_status"):
        active_matches = get_all_matches().filter(active=True).count()
        match_status = []
        if active_matches > 0:
            match_status.append("Active")
        if get_all_matches().filter(confirmed=True).exists():
            match_status.append("Confirmed")
        if get_all_matches().filter(completed=True).exists():
            match_status.append("Completed")
        if not match_status:
            match_status = ["No matches"]
        result["match_status"] = ", ".join(match_status)

    if include("match_details"):
        match_details = []
        for match in get_all_matches():
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
        result["match_details"] = match_details

    video_calls = None
    total_video_time_seconds_user = None

    def get_video_calls():
        nonlocal video_calls
        if video_calls is None:
            video_calls_as_u1 = LivekitSession.objects.filter(u1=user, both_have_been_active=True)
            video_calls_as_u2 = LivekitSession.objects.filter(u2=user, both_have_been_active=True)
            video_calls = video_calls_as_u1.union(video_calls_as_u2)
        return video_calls

    def get_total_video_time_seconds():
        nonlocal total_video_time_seconds_user
        if total_video_time_seconds_user is None:
            total_video_time_seconds_user = 0
            for call in get_video_calls():
                if call.end_time:
                    duration = call.end_time - call.created_at
                    total_video_time_seconds_user += duration.total_seconds()
        return total_video_time_seconds_user

    if include("total_video_calls"):
        result["total_video_calls"] = get_video_calls().count()

    if include("video_call_details"):
        video_call_details = []
        for call in get_video_calls():
            other_user = call.u1 if call.u1 != user else call.u2
            active_status = "Active" if call.is_active else "Inactive"

            if call.end_time:
                duration = call.end_time - call.created_at
                video_call_details.append(
                    {
                        "other_username": other_user.username,
                        "duration_seconds": duration.total_seconds(),
                        "status": active_status,
                    }
                )
            else:
                video_call_details.append({"other_username": other_user.username, "status": active_status})
        result["video_call_details"] = video_call_details

    if include("total_video_time_minutes"):
        result["total_video_time_minutes"] = round(get_total_video_time_seconds() / 60, 2)

    if include("total_video_time_hhmm"):
        result["total_video_time_hhmm"] = seconds_to_hhmm(get_total_video_time_seconds())

    if include("video_calls_with_most_recent_match") or include("messages_with_most_recent_match"):
        most_recent_match = get_all_matches().first()
        other_user = (
            most_recent_match.user2
            if most_recent_match and most_recent_match.user1 == user
            else (most_recent_match.user1 if most_recent_match else None)
        )

        if include("video_calls_with_most_recent_match"):
            result["video_calls_with_most_recent_match"] = (
                LivekitSession.objects.filter(
                    (Q(u1=user, u2=other_user) | Q(u1=other_user, u2=user)),
                    both_have_been_active=True,
                ).count()
                if other_user
                else 0
            )

        if include("messages_with_most_recent_match"):
            result["messages_with_most_recent_match"] = (
                Message.objects.filter(
                    Q(sender=user, recipient=other_user) | Q(sender=other_user, recipient=user)
                ).count()
                if other_user
                else 0
            )

    if include("messages_sent"):
        result["messages_sent"] = Message.objects.filter(sender=user).count()

    if include("messages_received"):
        result["messages_received"] = Message.objects.filter(recipient=user).count()

    if include("last_message_received"):
        last_message = Message.objects.filter(recipient=user).order_by("-created").first()
        result["last_message_received"] = datetime_to_readable_utc(last_message.created if last_message else None)

    if (
        include("last_user_to_support_message")
        or include("last_user_to_support_message_time")
        or include("last_support_to_user_reply")
        or include("last_support_to_user_reply_time")
    ):
        last_user_to_support_message, last_support_to_user_reply = get_latest_support_chat_messages(user)

        if include("last_user_to_support_message"):
            result["last_user_to_support_message"] = (
                last_user_to_support_message.text if last_user_to_support_message else None
            )
        if include("last_user_to_support_message_time"):
            result["last_user_to_support_message_time"] = datetime_to_readable_utc(
                last_user_to_support_message.created if last_user_to_support_message else None
            )
        if include("last_support_to_user_reply"):
            result["last_support_to_user_reply"] = (
                last_support_to_user_reply.text if last_support_to_user_reply else None
            )
        if include("last_support_to_user_reply_time"):
            result["last_support_to_user_reply_time"] = datetime_to_readable_utc(
                last_support_to_user_reply.created if last_support_to_user_reply else None
            )

    return result


# Must match keys returned by build_user_report_entry (used for lightweight export header discovery).
USER_EXPORT_COLUMN_NAMES = (
    "user_id",
    "vorname",
    "nachname",
    "email",
    "date_joined",
    "last_login",
    "german_language_level",
    "user_type",
    "expired_proposals_count",
    "user_journey_path",
    "match_status",
    "total_matches",
    "active_matches",
    "match_details",
    "video_call_details",
    "total_video_calls",
    "total_video_time_minutes",
    "total_video_time_hhmm",
    "messages_sent",
    "messages_received",
    "video_calls_with_most_recent_match",
    "messages_with_most_recent_match",
    "last_message_received",
    "last_user_to_support_message",
    "last_user_to_support_message_time",
    "last_support_to_user_reply",
    "last_support_to_user_reply_time",
)
