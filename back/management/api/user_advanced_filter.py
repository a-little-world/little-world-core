from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Subquery, OuterRef, Count, F
from management.models.unconfirmed_matches import ProposedMatch
from management.models.state import State
from management.models.user import User
from management.models.profile import Profile
from management.models.management_tasks import MangementTask
from management.models.pre_matching_appointment import PreMatchingAppointment
from chat.models import Message, Chat
from management.models.matches import Match
from management import controller


def three_weeks_ago():
    return timezone.now() - timedelta(weeks=3)


def all_users(qs=User.objects.all()):
    return qs.order_by("-date_joined")

def only_hd_test_user(qs=User.objects.all()):    
    return qs.filter(email__startswith="herrduenschnlate")

def needs_matching(qs=User.objects.all()):
    now = timezone.now()
    users_with_open_proposals = ProposedMatch.objects.filter(
        closed=False,
        expires_at__gt=now, 
        learner_when_created__isnull=False
    ).values_list('user1', 'user2')

    users_w_open_proposals = set([id for pair in users_with_open_proposals for id in pair])
    users_w_open_proposals = qs.filter(id__in=users_w_open_proposals)

    return (
        qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,  # TODO: filter should only be applied, if require_prematching_call = True
            state__searching_state=State.SearchingStateChoices.SEARCHING,
        ).exclude(id__in=users_w_open_proposals)
        .order_by("-date_joined")
    )


def needs_matching_volunteers(qs=User.objects.all()):
    return needs_matching(qs).filter(profile__user_type=Profile.TypeChoices.VOLUNTEER)


def searching_users(qs=User.objects.all()):
    return qs.filter(state__user_form_state=State.UserFormStateChoices.FILLED, state__email_authenticated=True, state__had_prematching_call=False, state__searching_state=State.SearchingStateChoices.SEARCHING).order_by("-date_joined")


def users_in_registration(qs=User.objects.all()):
    return qs.filter(Q(state__user_form_state=State.UserFormStateChoices.UNFILLED) | Q(state__email_authenticated=False) | Q(state__had_prematching_call=False)).order_by("-date_joined")


def active_within_3weeks(qs=User.objects.all()):
    return qs.filter(last_login__gte=three_weeks_ago()).order_by("-date_joined")


def get_active_match_query_set(qs=User.objects.all()):
    four_weeks_ago = timezone.now() - timedelta(weeks=4)
    senders = Message.objects.filter(created__gte=four_weeks_ago).values_list("sender", flat=True).distinct()
    return qs.filter(pk__in=senders)


def get_quality_match_query_set(qs=User.objects.all()):
    sq = Message.objects.filter(Q(sender=OuterRef("user1"), recipient=OuterRef("user2")) | Q(sender=OuterRef("user2"), recipient=OuterRef("user1"))).values("sender")
    matches_with_msg_count = Match.objects.filter(active=True).annotate(msg_count=Subquery(sq.annotate(cnt=Count("id")).values("cnt")[:1]))
    matches_with_enough_msgs = matches_with_msg_count.filter(msg_count__gte=20)
    return qs.filter(Q(match_user1__in=matches_with_enough_msgs) | Q(match_user2__in=matches_with_enough_msgs)).distinct().order_by("-date_joined")


def get_user_with_message_to_admin(qs=User.objects.all()):
    admin = controller.get_base_management_user()
    unread_messages = Message.objects.filter(recipient=admin, read=False).order_by("created")
    unread_senders_ids = unread_messages.values("sender")
    return qs.filter(id__in=Subquery(unread_senders_ids))


def user_recent_activity(qs=None, recent_days=60, min_recent_messages=1, min_recent_calls=0, min_recent_both_active_calls=0, include_signups=True):
    if qs is None:
        qs = User.objects.all()

    cutoff_date = timezone.now() - timedelta(days=recent_days)

    filtered_users = qs.filter(Q(u1_livekit_session__created_at__gte=cutoff_date) | Q(u2_livekit_session__created_at__gte=cutoff_date) | Q(message_sender__created__gte=cutoff_date)).distinct()

    filtered_users = filtered_users.annotate(
        recent_calls_u1=Count("u1_livekit_session", filter=Q(u1_livekit_session__created_at__gte=cutoff_date)),
        recent_calls_u2=Count("u2_livekit_session", filter=Q(u2_livekit_session__created_at__gte=cutoff_date)),
        both_active_calls_u1=Count("u1_livekit_session", filter=Q(u1_livekit_session__created_at__gte=cutoff_date, u1_livekit_session__both_have_been_active=True)),
        both_active_calls_u2=Count("u2_livekit_session", filter=Q(u2_livekit_session__created_at__gte=cutoff_date, u2_livekit_session__both_have_been_active=True)),
        recent_messages=Count("message_sender", filter=Q(message_sender__created__gte=cutoff_date)),
    ).filter(Q(recent_calls_u1__gte=min_recent_calls) | Q(recent_calls_u2__gte=min_recent_calls), Q(both_active_calls_u1__gte=min_recent_both_active_calls) | Q(both_active_calls_u2__gte=min_recent_both_active_calls), recent_messages__gte=min_recent_messages)

    # Handle recent signups
    if include_signups:
        recent_signups_completed_registration = qs.filter(
            date_joined__gte=cutoff_date,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
        ).distinct()

        filtered_users = filtered_users.union(recent_signups_completed_registration)

    # Ensure the result is distinct and ordered
    filtered_users = filtered_users.distinct().order_by("-date_joined")

    return filtered_users


def get_volunteers_booked_onboarding_call_but_never_visited(qs=User.objects.all()):
    user_with_onboarding_booked = PreMatchingAppointment.objects.all().values("user")
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED, state__email_authenticated=True, state__searching_state=State.SearchingStateChoices.SEARCHING, state__had_prematching_call=False, profile__user_type=Profile.TypeChoices.VOLUNTEER, state__unresponsive=False, pk__in=user_with_onboarding_booked
    ).order_by("-date_joined")


def get_user_with_message_to_admin_that_are_read_but_not_replied(qs=User.objects.all()):
    admin_pk = controller.get_base_management_user()
    dialogs_with_the_management_user = Chat.objects.filter(Q(u1=admin_pk) | Q(u2=admin_pk))
    last_message_per_user = Message.objects.filter((Q(sender_id=OuterRef("id"), recipient_id=admin_pk) | Q(sender_id=admin_pk, recipient_id=OuterRef("id")))).order_by("created").values("created")[:1]
    users_in_dialog_with_management_user = qs.annotate(last_message_id=Subquery(last_message_per_user.values("id")[:1])).filter(
        Q(last_message_id__in=Message.objects.filter(sender_id=F("id"), recipient_id=admin_pk, read=True)) | Q(last_message_id__in=Message.objects.filter(sender_id=admin_pk, recipient_id=F("id"), read=False))
    )
    return users_in_dialog_with_management_user


def users_with_open_proposals(qs=User.objects.all()):
    open_proposals = ProposedMatch.objects.filter(closed=False)
    return qs.filter(Q(pk__in=open_proposals.values("user1")) | Q(pk__in=open_proposals.values("user2"))).distinct().order_by("-date_joined")


def users_with_open_tasks(qs=User.objects.all()):
    open_tasks = MangementTask.objects.filter(state=MangementTask.MangementTaskStates.OPEN)
    return qs.filter(id__in=open_tasks.values("user"))


def users_with_booked_prematching_call(qs=User.objects.all()):
    user_with_prematching_booked = PreMatchingAppointment.objects.all().values("user")
    return qs.filter(state__user_form_state=State.UserFormStateChoices.FILLED, state__email_authenticated=True, state__searching_state=State.SearchingStateChoices.SEARCHING, state__had_prematching_call=False, state__unresponsive=False, pk__in=user_with_prematching_booked).order_by("-date_joined")


def users_require_prematching_call_not_booked(qs=User.objects.all()):
    user_with_prematching_booked = PreMatchingAppointment.objects.all().values("user")
    return qs.filter(state__user_form_state=State.UserFormStateChoices.FILLED, state__email_authenticated=True, state__searching_state=State.SearchingStateChoices.SEARCHING, state__had_prematching_call=False, state__unresponsive=False).exclude(pk__in=user_with_prematching_booked).order_by("-date_joined")

