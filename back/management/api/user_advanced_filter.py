from datetime import timedelta

from chat.models import Chat, Message
from django.db.models import Count, F, OuterRef, Q, Subquery, Case, When
from django.db.models.functions import Extract
from django.utils import timezone

from management import controller
from management.models.management_tasks import MangementTask
from management.models.matches import Match
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.profile import Profile
from management.models.state import State
from management.models.unconfirmed_matches import ProposedMatch
from management.models.user import User


def three_weeks_ago():
    return timezone.now() - timedelta(weeks=3)


def all_users(qs=User.objects.all()):
    """
    All users ordered by date joined!
    """
    return qs.order_by("-date_joined")


def only_hd_test_user(qs=User.objects.all()):
    """
    TESTING: Just a list of some test users for tim
    """
    return qs.filter(email__startswith="herrduenschnlate")


def needs_matching(qs=User.objects.all(), learner_atleast_searching_for_x_days=-1):
    """
    All users in 'searching' without any user that has an open proposal!
    Optionally, for learners, only include those who have been searching for at least X days.
    """
    now = timezone.now()
    users_with_open_proposals = ProposedMatch.objects.filter(
        closed=False, expires_at__gt=now, learner_when_created__isnull=False
    ).values_list("user1", "user2")

    users_w_open_proposals = set([id for pair in users_with_open_proposals for id in pair])
    users_w_open_proposals = qs.filter(id__in=users_w_open_proposals)

    base_qs = (
        qs.filter(
            is_active=True,
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__unresponsive=False,
            state__had_prematching_call=True,  # TODO: filter should only be applied, if require_prematching_call = True
            state__searching_state=State.SearchingStateChoices.SEARCHING,
        )
        .exclude(id__in=users_w_open_proposals)
        .order_by("-date_joined")
    )

    if learner_atleast_searching_for_x_days != -1:
        # For learners, calculate waiting time using database queries
        learners = base_qs.filter(profile__user_type=Profile.TypeChoices.LEARNER)
        
        # Get the latest pre-matching appointment for each learner
        latest_appointments = PreMatchingAppointment.objects.filter(
            user__in=learners
        ).order_by('user', '-created').distinct('user')
        
        # Calculate days since appointment or state update
        waiting_time = Case(
            # If user has matches, use state update time
            When(
                Q(match_user1__support_matching=False) | Q(match_user2__support_matching=False),
                then=Extract(timezone.now() - F('state__searching_state_last_updated'), 'day')
            ),
            # Otherwise use pre-matching appointment end time
            default=Extract(
                timezone.now() - Subquery(
                    latest_appointments.filter(user=OuterRef('pk')).values('end_time')[:1]
                ),
                'day'
            )
        )
        
        # Annotate learners with their waiting time
        learners = learners.annotate(waiting_days=waiting_time)
        
        # Filter learners based on waiting time
        filtered_learners = learners.filter(
            Q(waiting_days__gte=learner_atleast_searching_for_x_days) |
            Q(waiting_days__isnull=True)  # Include users without waiting time calculation
        )
        
        # Combine filtered learners with non-learners
        non_learners = base_qs.exclude(profile__user_type=Profile.TypeChoices.LEARNER)
        return base_qs.filter(
            Q(id__in=filtered_learners.values_list('id', flat=True)) |
            Q(id__in=non_learners.values_list('id', flat=True))
        ).order_by("-date_joined")
    else:
        return base_qs


def needs_matching_volunteers(qs=User.objects.all()):
    """
    Volunteers only: All users in 'searching' without any user that has an open proposal!
    """
    return needs_matching(qs).filter(profile__user_type=Profile.TypeChoices.VOLUNTEER)


def searching_users(qs=User.objects.all()):
    """
    Users who are currently searching for a match
    """
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__had_prematching_call=False,
        state__searching_state=State.SearchingStateChoices.SEARCHING,
    ).order_by("-date_joined")


def users_in_registration(qs=User.objects.all()):
    """
    Users who have not finished the user form or verified their email!
    """
    return qs.filter(
        Q(state__user_form_state=State.UserFormStateChoices.UNFILLED)
        | Q(state__email_authenticated=False)
        | Q(state__had_prematching_call=False)
    ).order_by("-date_joined")


def active_within_3weeks(qs=User.objects.all()):
    """
    Users who have been active within the last 3 weeks!
    """
    return qs.filter(last_login__gte=three_weeks_ago()).order_by("-date_joined")


def get_active_match_query_set(qs=User.objects.all()):
    """
    Users who have communicated with their match in the last 4 weeks
    """
    four_weeks_ago = timezone.now() - timedelta(weeks=4)
    senders = Message.objects.filter(created__gte=four_weeks_ago).values_list("sender", flat=True).distinct()
    return qs.filter(pk__in=senders)


def get_quality_match_query_set(qs=User.objects.all()):
    """
    Users who have at least one matching with 20+ Messages
    """
    sq = Message.objects.filter(
        Q(sender=OuterRef("user1"), recipient=OuterRef("user2"))
        | Q(sender=OuterRef("user2"), recipient=OuterRef("user1"))
    ).values("sender")
    matches_with_msg_count = Match.objects.filter(active=True).annotate(
        msg_count=Subquery(sq.annotate(cnt=Count("id")).values("cnt")[:1])
    )
    matches_with_enough_msgs = matches_with_msg_count.filter(msg_count__gte=20)
    return (
        qs.filter(Q(match_user1__in=matches_with_enough_msgs) | Q(match_user2__in=matches_with_enough_msgs))
        .distinct()
        .order_by("-date_joined")
    )


def get_user_with_message_to_admin(qs=User.objects.all()):
    """
    Users who have an unread message to the admin user
    """
    admin = controller.get_base_management_user()
    unread_messages = Message.objects.filter(recipient=admin, read=False).order_by("created")
    unread_senders_ids = unread_messages.values("sender")
    return qs.filter(id__in=Subquery(unread_senders_ids))


def user_recent_activity(
    qs=None,
    recent_days=60,
    min_recent_messages=1,
    min_recent_calls=0,
    min_recent_both_active_calls=0,
    include_signups=True,
):
    if qs is None:
        qs = User.objects.all()

    cutoff_date = timezone.now() - timedelta(days=recent_days)

    filtered_users = qs.filter(
        Q(u1_livekit_session__created_at__gte=cutoff_date)
        | Q(u2_livekit_session__created_at__gte=cutoff_date)
        | Q(message_sender__created__gte=cutoff_date)
    ).distinct()

    filtered_users = filtered_users.annotate(
        recent_calls_u1=Count(
            "u1_livekit_session",
            filter=Q(u1_livekit_session__created_at__gte=cutoff_date),
        ),
        recent_calls_u2=Count(
            "u2_livekit_session",
            filter=Q(u2_livekit_session__created_at__gte=cutoff_date),
        ),
        both_active_calls_u1=Count(
            "u1_livekit_session",
            filter=Q(
                u1_livekit_session__created_at__gte=cutoff_date,
                u1_livekit_session__both_have_been_active=True,
            ),
        ),
        both_active_calls_u2=Count(
            "u2_livekit_session",
            filter=Q(
                u2_livekit_session__created_at__gte=cutoff_date,
                u2_livekit_session__both_have_been_active=True,
            ),
        ),
        recent_messages=Count("message_sender", filter=Q(message_sender__created__gte=cutoff_date)),
    ).filter(
        Q(recent_calls_u1__gte=min_recent_calls) | Q(recent_calls_u2__gte=min_recent_calls),
        Q(both_active_calls_u1__gte=min_recent_both_active_calls)
        | Q(both_active_calls_u2__gte=min_recent_both_active_calls),
        recent_messages__gte=min_recent_messages,
    )

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
    """
    Volunteers who have booked an onboarding call but never visited
    """
    user_with_onboarding_booked = PreMatchingAppointment.objects.all().values("user")
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__had_prematching_call=False,
        profile__user_type=Profile.TypeChoices.VOLUNTEER,
        state__unresponsive=False,
        pk__in=user_with_onboarding_booked,
    ).order_by("-date_joined")


def get_user_with_message_to_admin_that_are_read_but_not_replied(qs=User.objects.all()):
    """
    Read messages to the management user that have not been replied to
    """
    admin_pk = controller.get_base_management_user()
    dialogs_with_the_management_user = Chat.objects.filter(Q(u1=admin_pk) | Q(u2=admin_pk))
    last_message_per_user = (
        Message.objects.filter(
            (Q(sender_id=OuterRef("id"), recipient_id=admin_pk) | Q(sender_id=admin_pk, recipient_id=OuterRef("id")))
        )
        .order_by("created")
        .values("created")[:1]
    )
    users_in_dialog_with_management_user = qs.annotate(
        last_message_id=Subquery(last_message_per_user.values("id")[:1])
    ).filter(
        Q(last_message_id__in=Message.objects.filter(sender_id=F("id"), recipient_id=admin_pk, read=True))
        | Q(last_message_id__in=Message.objects.filter(sender_id=admin_pk, recipient_id=F("id"), read=False))
    )
    return users_in_dialog_with_management_user


def users_with_open_proposals(qs=User.objects.all()):
    """
    Users who have open proposals
    """
    open_proposals = ProposedMatch.objects.filter(closed=False)
    return (
        qs.filter(Q(pk__in=open_proposals.values("user1")) | Q(pk__in=open_proposals.values("user2")))
        .distinct()
        .order_by("-date_joined")
    )


def users_with_open_tasks(qs=User.objects.all()):
    """
    Users who have open tasks
    """
    open_tasks = MangementTask.objects.filter(state=MangementTask.MangementTaskStates.OPEN)
    return qs.filter(id__in=open_tasks.values("user"))


def users_with_booked_prematching_call(qs=User.objects.all()):
    """
    Users that have booked a pre-matching call
    """
    user_with_prematching_booked = PreMatchingAppointment.objects.all().values("user")
    return qs.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__had_prematching_call=False,
        state__unresponsive=False,
        pk__in=user_with_prematching_booked,
    ).order_by("-date_joined")


def users_require_prematching_call_not_booked(qs=User.objects.all()):
    """
    Users that still require a pre-matching call before matching, but haven't booked one yet
    """
    user_with_prematching_booked = PreMatchingAppointment.objects.all().values("user")
    return (
        qs.filter(
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__searching_state=State.SearchingStateChoices.SEARCHING,
            state__had_prematching_call=False,
            state__unresponsive=False,
        )
        .exclude(pk__in=user_with_prematching_booked)
        .order_by("-date_joined")
    )
