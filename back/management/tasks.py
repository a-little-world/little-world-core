from cookie_consent.models import CookieGroup, Cookie
from celery import shared_task
from tracking.utils import inline_track_event
from dataclasses import dataclass
from .models import User
import datetime
from django.utils.translation import pgettext_lazy
from .models.community_events import CommunityEvent, CommunityEventSerializer
from .models.backend_state import BackendState
"""
also contains general startup celery tasks, most of them are automaticly run when the controller.get_base_management user is created
some of them are managed via models.backend_state.BackendState to ensure they don't run twice!
If you wan't to rerun one of these events make sure to delete the old data *and* the backend state slug!
"""


@shared_task
def create_default_community_events():
    """
    Creates base community events,
    we store this here since we are using translations here!
    Tough we do default to german here for now!
    """
    if BackendState.are_default_community_events_set(set_true=True):
        return "events already set, sais backend state! If they where deleted you should delete the state!"

    CommunityEvent.objects.create(
        title=pgettext_lazy('community-event.coffe-chillout', 'Kaffeerunden'),
        description="Zusammenkommen der Community – lerne das Team hinter Little World und andere Nutzer:innen bei einer gemütlichen Tasse Kaffee oder Tee kennen.",
        time=datetime.datetime(2022, 11, 29, 12, 00, 00,
                               00, datetime.timezone.utc),
        active=True,
        frequency=CommunityEvent.EventFrequencyChoices.WEEKLY
    )

    return "events created!"


@shared_task
def create_default_cookie_groups():
    if BackendState.are_default_cookies_set(set_true=True):
        return "events already set, sais backend state! If they where deleted you should delete the state!"

    analytics_cookiegroup = CookieGroup.objects.create(
        varname="analytics",
        name="analytics_cookiegroup",
        description="Google analytics and Facebook Pixel",
        is_required=False,
        is_deletable=True
    )

    little_world_functionality_cookies = CookieGroup.objects.create(
        varname="lw_func_cookies",
        name="FunctionalityCookies",
        description="Cookies required for basic functionality of Little World",
        is_required=True,
        is_deletable=False
    )

    google_analytics_cookie = Cookie.objects.create(
        cookiegroup=analytics_cookiegroup,
        name="google_analytics_cookie",
        description="Google anlytics cookies and scripts",
        include_srcs=[
            "https://www.googletagmanager.com/gtag/js?id=AW-10994486925"],
        include_scripts=[
            "\nwindow.dataLayer = window.dataLayer || [];\n" +
            "function gtag(){dataLayer.push(arguments);}\n" +
            "gtag('js', new Date());\n" +
            "gtag('config', 'AW-10994486925');\n" +
            "gtag('config', 'AW-10992228532');"
        ],
    )

    facebook_init_script = "\n!function(f,b,e,v,n,t,s)\n{if(f.fbq)return;n=f.fbq=function(){n.callMethod?\n" + \
        "n.callMethod.apply(n,arguments):n.queue.push(arguments)};\nif(!f._fbq)f._fbq=n;n.push=n;" + \
        "n.loaded=!0;n.version='2.0';\nn.queue=[];t=b.createElement(e);t.async=!0;\nt.src=v;s=b.getElementsByTagName(e)[0];" + \
        "\ns.parentNode.insertBefore(t,s)}(window, document,'script',\n'https://connect.facebook.net/en_US/fbevents.js');\n" + \
        "fbq('init', '1108875150004843');\nfbq('track', 'PageView');\n    "

    facebook_pixel_cookie = Cookie.objects.create(
        cookiegroup=analytics_cookiegroup,
        name="facebook_pixel_cookie",
        description="Facebook Pixel analytics cookies and scripts",
        include_srcs=[],
        include_scripts=[facebook_init_script],
    )
    return "RES"


@shared_task
def fill_base_management_user_profile():
    """
    Fills our required fields for the admin user in the background
    """
    if BackendState.is_base_management_user_profile_filled(set_true=True):
        return  # Allready filled base management user profile

    from .controller import get_base_management_user

    base_management_user_description = """
Hey :)
ich bin Oliver, einer der Gründer und dein persönlicher Ansprechpartner für Fragen & Anregungen.

Selbst habe ich vier Jahre im Ausland gelebt, von Frankreich bis nach China. Den interkulturellen Austausch habe ich immer geliebt, wobei mich die Gastfreundschaft oft tief beeindruckt hat.
"""
    usr = get_base_management_user()
    usr.profile.birth_year = 1984
    usr.profile.postal_code = 20480
    usr.profile.description = base_management_user_description
    usr.profile.add_profile_picture_from_local_path(
        '/back/dev_test_data/oliver_berlin_management_user_profile_pic.jpg')
    usr.profile.save()
    usr.profile.save()
    return "sucessfully filled base management user profile"


@shared_task
def calculate_directional_matching_score_background(
    usr_hash,
    catch_exceptions=True,
    filter_slugs=None,
    invalidate_other_scores=False
):
    """
    This is the backend task for calculating a matching score.
    This will *automaticly* be executed everytime a users changes his user form
    run with calculate_directional_matching_score_background.delay(usr)
    """
    print(f"Calculating score for {usr_hash}")
    from .controller import get_user_by_hash
    from .matching.matching_score import calculate_directional_score_write_results_to_db
    from .models import State, MatchinScore

    usr = get_user_by_hash(usr_hash)

    # We only search for all users that are searching
    # But since the search is generally triggered by the user searching
    # -> this will keep all matching scores up to date always
    if filter_slugs is None:
        all_users_to_consider = User.objects.all() \
            .exclude(id=usr.id) \
            .exclude(state__matching_state=State.MatchingStateChoices.IDLE)
    else:
        from .api.user_slug_filter_lookup import get_filter_slug_filtered_users_multiple
        all_users_to_consider = get_filter_slug_filtered_users_multiple(
            filters=filter_slugs
        )
    print("CONSIDERING", all_users_to_consider)
    for other_usr in all_users_to_consider:
        print(f"Calculating score {usr} -> {other_usr}")
        score1 = calculate_directional_score_write_results_to_db(
            usr, other_usr, return_on_nomatch=False,
            catch_exceptions=catch_exceptions)
        print(f"Calculating score {other_usr} -> {usr}")
        score2 = calculate_directional_score_write_results_to_db(
            other_usr, usr, return_on_nomatch=False,
            catch_exceptions=catch_exceptions)

    if invalidate_other_scores:
        for other_user in User.objects.exclude(id=usr.id):
            if other_user not in all_users_to_consider:
                cur_score = MatchinScore.get_current_directional_score(
                    from_usr=usr,
                    to_usr=other_user,
                    raise_exeption=False
                )
                print(f"Invalidating score {usr.id}")
                if not cur_score is None:
                    cur_score.set_to_old()


@shared_task
def create_default_table_score_source():
    if BackendState.is_default_score_source_created(set_true=True):
        return "default score source already created"

    from .models.matching_scores import ScoreTableSource
    from .matching.matching_score import SCORING_FUNCTIONS
    from .matching.score_table_lookup import (
        TARGET_GROUP_SCORES,
        TARGET_GROUP_MESSAGES,
        PARTNER_LOCATION_SCORES,
        LANGUAGE_LEVEL_SCORES,
        SPEECH_MEDIUM_SCORES
    )

    ScoreTableSource.objects.create(
        target_group_scores=TARGET_GROUP_SCORES,
        target_group_messages=TARGET_GROUP_MESSAGES,
        partner_location_scores=PARTNER_LOCATION_SCORES,
        language_level_scores=LANGUAGE_LEVEL_SCORES,
        speech_medium_scores=SPEECH_MEDIUM_SCORES,
        # Per default select **all** scoring functions
        function_scoring_selection=list(SCORING_FUNCTIONS.keys())
    )
    return "default score source created"


@shared_task
def dispatch_track_chat_channel_event(
    message_type: str,
    usr_hash: str,
    meta: dict
):
    """
    Automaticly triggered by some events in management.app.chat
    types:    connected | disconnected | message-send
    """
    from .controller import get_user_by_hash
    caller = "anonymous"
    try:
        caller = get_user_by_hash(usr_hash)
    except:
        print("Could not find user by hash", usr_hash)

    inline_track_event(
        caller=caller,
        tags=["chat", "channels", message_type],
        channel_meta=meta
    )


@shared_task
def archive_current_profile_user(usr_hash):
    """
    Task is called when a user changed this searching state, it will archive the current profile
    """

    from .models.profile import ProfileAtMatchRequest, SelfProfileSerializer
    from .controller import get_user_by_hash
    profile = get_user_by_hash(usr_hash).profile
    data = SelfProfileSerializer(profile).data
    _d = {k: data[k]
          for k in data if not k in ["options"]}  # Filter out options
    ProfileAtMatchRequest.objects.create(
        usr_hash=usr_hash,
        **data
    )


@shared_task
def send_new_message_notifications_all_users(
    filter_out_base_user_messages=True,
    do_send_emails=True,
    do_write_new_state_to_db=True,
    send_only_if_logged_in_withing_last_3_weeks=False
):
    """
    First we need to caluculate how many new messages per chat there are
    Then we check if this are more unread messages than before
    """
    from django.conf import settings
    from back.utils import CoolerJson
    # user = controller.get_user_by_hash(user_hash)
    from chat.django_private_chat2.models import MessageModel, DialogsModel
    from . import controller
    from emails import mails
    from .models import User

    if settings.IS_STAGE or settings.IS_DEV:
        return "Not caluculating or sending new messages cause in dev or in staging environment"

    def is_dialog_in_old_unread_stack(dialog_id, old_unread_stack):
        for urstd in old_unread_stack:
            if urstd["dialog_id"] == dialog_id:
                return urstd
        return None

    base_management_user = controller.get_base_management_user()
    # test1_user = controller.get_user_by_email("test1@user.de")
    users_to_send_update_to = []
    users_to_old_unread_stack = {}
    users_to_new_unread_stack = {}

    users = User.objects.all()
    # users = users.filter(email="herrduenschnlate@gmail.com")
    print("Prefiltered users", users.count())
    for user in users:
        print("==== checking ===> ", user.email, user.hash)
        dialogs = DialogsModel.get_dialogs_for_user_as_object(user)
        print("DIAZZZ", dialogs)
        new_unread_stack = []
        for dialog in dialogs:

            other_user = dialog.user1 if dialog.user1 != user else dialog.user2

            unread = MessageModel.get_unread_count_for_dialog_with_user(
                other_user, user)
            last_message = MessageModel.get_last_message_object_for_dialog(
                dialog.user1, dialog.user2)
            if last_message is None:
                print("WARN, mesasge object empty")
                continue
            print("UNREAD OF THAT", unread, last_message.text)

            if unread > 0:

                urstd = {
                    "unread_count": unread,
                    "dialog_id": dialog.id,
                    "other_user_hash": user.hash,
                    "last_message_id": last_message.id,
                }

                if filter_out_base_user_messages and base_management_user.hash == other_user.hash:
                    print("Not added since from base admin", urstd)
                else:
                    new_unread_stack.append(urstd)
                    print("updated unread", urstd)

        # Now we can load the old unread stack
        print("Checking last unread state", user.state.unread_messages_state)
        current_unread_state = user.state.unread_messages_state
        users_to_old_unread_stack[user.email] = current_unread_state
        for unread_state in new_unread_stack:
            old_dialog = is_dialog_in_old_unread_stack(
                unread_state["dialog_id"], current_unread_state)

            if old_dialog is None:
                # Then we know this is definately a new dialog, we need to notifiy about
                print("Completely new dialog unread state", unread_state)
            else:
                if old_dialog["last_message_id"] != unread_state["last_message_id"]:
                    # Then we know there is another new mesasage in a disalog we need to notify about
                    # So wee need to delete the old dialog refernce in the current model
                    current_unread_state.remove(old_dialog)
                    print(
                        "Found new unread state for dialog that already had unreads", unread_state)
                else:
                    # Then this is not a new unread message so we need to remove it from the stack
                    print("Found old unread state",
                          unread_state, ", removing...")
                    new_unread_stack.remove(unread_state)

        print("Filtered for new unread states: ",
              new_unread_stack, current_unread_state)
        users_to_new_unread_stack[user.email] = new_unread_stack
        if do_write_new_state_to_db:
            user.state.unread_messages_state = current_unread_state + new_unread_stack
            user.state.save()
            print("Saved updated state", user.state.unread_messages_state)
        if len(new_unread_stack) > 0:
            # Now we can sendout the notifications email
            print("\n\nSEND update to", user.email, user.hash)
            if send_only_if_logged_in_withing_last_3_weeks:
                from django.utils import timezone
                today = timezone.now()
                tree_weeks = datetime.timedelta(days=7*3)
                tree_weeks_ago = today - tree_weeks
                if user.last_login < tree_weeks_ago:
                    print("WARN, user not logged in for 3 weeks")
                    continue
                else:
                    users_to_send_update_to.append(user)
            else:
                users_to_send_update_to.append(user)

    for u in users_to_send_update_to:
        print("Notifying ", u.email)
        if False:  # do_send_emails:
            u.send_email(
                subject=pgettext_lazy(
                    "tasks.unread-notifications-email-subject", "Neue Nachricht(en) auf Little World"),
                mail_data=mails.get_mail_data_by_name("new_messages"),
                mail_params=mails.NewUreadMessagesParams(
                    first_name=u.profile.first_name,
                )
            )
    print("Summary: ",
          f"\namount notifications: {len(users_to_send_update_to)}")
    import json
    return {
        "emailed_users": [u.email for u in users_to_send_update_to],
        "stack": json.loads(json.dumps(users_to_new_unread_stack, cls=CoolerJson)),
        "stack_old": json.loads(json.dumps(users_to_old_unread_stack, cls=CoolerJson))
    }


@shared_task
def write_hourly_backend_event_summary(
    start_time=None
):
    """
    Collects a bunch of stats and stores them as tracking.models.Summaries

    - users registered today
    - users verified email today
    - users filled user form today
    - users logged in today
    - users send messages today
    - users had a call together today
    - users total time connected to chat
    - users mean call time today
    - amount messages sent today
    - amount matches created today
    """

    from tracking.models import Summaries, Event
    from management.models import User
    from datetime import timedelta
    from django.utils import timezone

    # For that fist we extract all event within that hour
    time = timezone.now()
    if start_time is not None:
        time = start_time  # TODO: prob need serializable format

    this_hour = time.replace(minute=0, second=0, microsecond=0)
    one_hour_later = this_hour + timedelta(hours=4)
    earlier = this_hour - timedelta(hours=4)
    events = Event.objects.filter(time__range=(this_hour, one_hour_later))

    chat_connections_per_user = {}
    new_user_registrations = []
    users_called_login_api = []
    users_sucessfully_logged_in = []
    users_changed_profile = []
    users_logged_out = []
    call_rooms_authenticated = []
    matches_made = []
    absolute_requests_tracked = 0

    def init_connection_hash_is_empty(hash):
        if not hash in chat_connections_per_user:
            chat_connections_per_user[hash] = {
                "connected": [],
                "disconnected": [],
                "send_messages_count": 0
            }

    for event in events:
        # print("TIME", event.time)
        has_event_tags = hasattr(
            event, "tags") and isinstance(event.tags, list)
        has_caller_annotation = hasattr(event, "caller")

        caller_hash = None

        try:
            caller_hash = event.caller.hash
        except:
            pass

        if event.name == "request":
            absolute_requests_tracked += 1

        if has_event_tags and has_caller_annotation and caller_hash is not None:
            assert isinstance(event.tags, list)

            if all([x in event.tags for x in ["backend", "function", "db"]]):
                m = [(None, None)]
                try:
                    m[0] = event.metadata["args"][0]
                except:
                    pass

                matches_made += m

            if all([x in event.tags for x in ['frontend', 'login']]):
                # Try to extract the login user email
                if 'request_data1' in event.metadata and 'email' in event.metadata['request_data1']:
                    users_called_login_api.append(
                        event.metadata['request_data1']['email'])
                elif 'request_data2' in event.metadata and 'email' in event.metadata['request_data2']:
                    users_called_login_api.append(
                        event.metadata['request_data2']['email'])
                else:
                    print("Login attepted but couldn't retrive email")

            if all([x in event.tags for x in ['chat', 'channels', 'connected']]):
                # User connected to chat
                init_connection_hash_is_empty(caller_hash)
                chat_connections_per_user[caller_hash]["connected"].append(
                    event.time)

            if all([x in event.tags for x in ['chat', 'channels', 'disconnected']]):
                # User connected to chat
                init_connection_hash_is_empty(caller_hash)
                chat_connections_per_user[caller_hash]["disconnected"].append(
                    event.time)

            if all([x in event.tags for x in ['chat', 'channels', 'message-send']]):
                init_connection_hash_is_empty(caller_hash)
                chat_connections_per_user[caller_hash]["send_messages_count"] += 1

    # Now see how many users actually sucessfully loggedin during that hour
    for u in User.objects.filter(last_login__range=(this_hour, one_hour_later)):
        users_sucessfully_logged_in.append(u)

    for u in User.objects.filter(profile__updated_at__range=(this_hour, one_hour_later)):
        users_changed_profile.append(u)

    summary_meta = dict(
        chat_connections_per_user=chat_connections_per_user,
        new_user_registrations=new_user_registrations,
        users_called_login_api=users_called_login_api,
        users_sucessfully_logged_in=users_sucessfully_logged_in,
        users_changed_profile=users_changed_profile,
        users_logged_out=users_logged_out,
        call_rooms_authenticated=call_rooms_authenticated,
        absolute_requests_tracked=absolute_requests_tracked,
        matches_made=matches_made,
        absoulte_matches_made=len(matches_made),
    )

    return summary_meta


@shared_task
def delete_all_old_matching_scores():
    from .models import MatchinScore
    count = MatchinScore.objects.all().count()
    c = 0
    for s in range(count):
        score = MatchinScore.objects.filter(pk=s).first()
        if score is not None:
            print(f"Check score for deletion {c}/{count}")
            if not score.current_score:
                c += 1
                score.delete()


@shared_task
def dispatch_admin_email_notification(subject, message):
    from . import controller
    from emails import mails
    base_management_user = controller.get_base_management_user()

    base_management_user.send_email(
        subject=subject,
        mail_data=mails.get_mail_data_by_name("raw"),
        mail_params=mails.RAWTemplateMailParams(
            subject_header_text=subject,
            greeting=message,
            content_start_text=message
        )
    )
