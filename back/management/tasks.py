from datetime import datetime
from cookie_consent.models import CookieGroup, Cookie
from celery import shared_task
from tracking.utils import inline_track_event
from dataclasses import dataclass
from .models import User
import datetime
from django.utils.translation import pgettext_lazy
from .models.community_events import CommunityEvent, CommunityEventSerializer
from .models.backend_state import BackendState
import operator
from functools import reduce
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
    filter_out_base_user_messages=False,
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
    # users = users.filter(email="jimmyhendrix1024@gmail.com")
    print("Prefiltered users", users.count())
    for user in users:
        print("==== checking ===> ", user.email, user.hash)
        dialogs = DialogsModel.get_dialogs_for_user_as_object(user)
        print("DIAZZZ", dialogs)
        new_unread_stack = []
        for dialog in dialogs:

            other_user = dialog.user1 if dialog.user1 != user else dialog.user2
            print("THE other guy is", other_user.email)

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
                    print("\n NEW UNREAD STATE", new_unread_stack, "\n")

        # Now we can load the old unread stack
        print("Checking last unread state", user.state.unread_messages_state)
        current_unread_state = user.state.unread_messages_state
        users_to_old_unread_stack[user.email] = current_unread_state
        print("SCANNING OLD STATES: \n")

        new_unread_stack_copy = new_unread_stack.copy()
        for unread_state in new_unread_stack:
            print("\nNEW DIA", unread_state, "\n")
            old_dialog = is_dialog_in_old_unread_stack(
                unread_state["dialog_id"], current_unread_state)

            if old_dialog is None:
                # Then we know this is definately a new dialog, we need to notifiy about
                print("Completely new dialog unread state", unread_state)
            else:
                print("OLD DIA ", old_dialog)
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
                    print("\nBREFORE DELETE", new_unread_stack)
                    new_unread_stack_copy.remove(unread_state)
                    print("\nAFTER DELETE", new_unread_stack_copy, "\n")

        new_unread_stack = new_unread_stack_copy
        print("\n UNREAD AFTER", new_unread_stack, "\n")

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
        # do_send_emails:
        if not (settings.IS_STAGE or settings.IS_DEV) and do_send_emails:
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
    start_time=None,
    end_time=None,
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
    from datetime import timedelta, datetime
    from django.utils import timezone
    from . import controller

    # For that fist we extract all event within that hour
    # We calculate from 2 hours ago per default cause otherwise the task could be shedules eventhought the hour is not completed yet
    time = timezone.now() - timedelta(hours=1)
    if start_time is not None:
        time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S.%f')

    this_hour = time.replace(minute=0, second=0, microsecond=0)
    one_hour_later = this_hour + timedelta(hours=1)
    if end_time is not None:
        one_hour_later = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S.%f')
    events = Event.objects.filter(time__range=(this_hour, one_hour_later))

    event_count = events.count()
    print("Found" + str(event_count) + "events in that hour")

    chat_connections_per_user = {}
    chat_interations_per_dialog = {}
    new_user_registrations = []
    users_called_login_api = []
    users_sucessfully_logged_in = []
    users_changed_profile = []
    users_logged_out = []
    call_rooms_authenticated = []
    matches_made = []
    connection_disconnection_events = []
    event_errors = []
    volunteer_learner_registration_ration = 0.0
    absolute_requests_tracked = 0

    def init_connection_hash_is_empty(hash):
        if not hash in chat_connections_per_user:
            chat_connections_per_user[hash] = {
                "connected": [],
                "disconnected": [],
                "send_messages_count": 0
            }

    def init_dialog_in_chat_interaction(id_combined):
        if not id_combined in chat_interations_per_dialog:
            chat_interations_per_dialog[id_combined] = {
                "amnt_msgs_send": 0,
                "msgs": []
            }

    i = -1
    for event in events:
        # print("TIME", event.time)
        i += 1
        print(f"Processing event ({i}/{event_count})")
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

            if all([x in event.tags for x in ['frontend', 'log-out']]):
                if event.caller:
                    users_logged_out.append(event.caller.hash)

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
                print("TBS metadata", event.metadata)
                pk1, pk2 = event.metadata["kwargs"]["channel_meta"]["from_pk"], event.metadata["kwargs"]["channel_meta"]["to_pk"]
                pk1, pk2 = int(pk1), int(pk2)
                if pk1 < pk2:
                    slug = f"{pk1}-{pk2}"
                else:
                    slug = f"{pk1}-{pk2}"
                init_dialog_in_chat_interaction(slug)
                chat_interations_per_dialog[slug]["amnt_msgs_send"] += 1
                chat_interations_per_dialog[slug]["msgs"].append(
                    {**event.metadata["kwargs"]["channel_meta"], "time": event.time})
                chat_connections_per_user[caller_hash]["send_messages_count"] += 1
        elif has_event_tags:
            # Stuff that doesnt have caller annotations

            if all([x in event.tags for x in ['frontend', 'login']]):
                # Try to extract the login user email
                if 'request_data1' in event.metadata and 'email' in event.metadata['request_data1']:
                    mail = event.metadata['request_data1']['email'][0]
                    hash = "unknown"
                    try:
                        hash = controller.get_user_by_email(mail.strip()).hash
                    except:
                        pass
                    users_called_login_api.append({"e": mail, "h": hash})
                elif 'request_data2' in event.metadata and 'email' in event.metadata['request_data2']:
                    mail = event.metadata['request_data1']['email'][0]
                    hash = "unknown"
                    try:
                        hash = controller.get_user_by_email(mail.strip()).hash
                    except:
                        pass
                    users_called_login_api.append({"e": mail, "h": hash})
                else:
                    print("Login attepted but couldn't retrive email")

            if all([x in event.tags for x in ["backend", "function", "db"]]):
                m = [(None, None)]
                other_user_with_management = None
                try:
                    m[0] = event.metadata["args"][0]
                    if m[0][1] == "littleworld.management@gmail.com":
                        other_user_with_management = m[0][0]
                    elif m[0][0] == "littleworld.management@gmail.com":
                        other_user_with_management = m[0][1]
                except:
                    pass

                # Every match that is made with the admin base user implies that a new user has registered
                if other_user_with_management is not None:
                    # TODO: in the future this check should be performed differently
                    new_user_registrations.append(other_user_with_management)
                else:
                    matches_made += m

            if all([x in event.tags for x in ['remote', 'twilio']]):
                if 'request_data1' in event.metadata and 'RoomName' in event.metadata['request_data1']:
                    # 'participant-disconnected' or 'participant-connected'
                    from .models import Room
                    # Lookup the room add both users
                    try:
                        room_name = event.metadata['request_data1']['RoomName'][0]
                        room = Room.get_room_by_hash(room_name)
                        participant = event.metadata['request_data1']['ParticipantIdentity'][0]
                        status_event = event.metadata['request_data1']['StatusCallbackEvent'][0]
                        if status_event in ["participant-connected", "participant-disconnected"]:
                            connection_disconnection_events.append({
                                "time": event.time,
                                "timestamp": event.metadata['request_data1']['Timestamp'],
                                "room_name": room_name,
                                "room_users": [room.usr1.hash, room.usr2.hash],
                                "event": status_event,
                                "actor": participant
                            })
                    except Exception as e:
                        print(f"Count retrive room {room_name}")
                        event_errors.append(str(e) + str(event.metadata))

    total_volunteers = 0
    total_learners = 0

    for mail in new_user_registrations:
        try:
            _u = controller.get_user_by_email(mail)
            if _u.profile.user_type == "volunteer":
                total_volunteers += 1
            else:
                total_learners += 1
        except:
            pass

    # Now see how many users actually sucessfully loggedin during that hour
    for u in User.objects.filter(last_login__range=(this_hour, one_hour_later)):
        users_sucessfully_logged_in.append(u.hash)

    for u in User.objects.filter(profile__updated_at__range=(this_hour, one_hour_later)):
        users_changed_profile.append(u.hash)

    import json
    from back.utils import CoolerJson

    total_amount_of_users = User.objects.count()
    if False:
        total_matches = 0
        c = 0
        for u in User.objects.exclude(id=controller.get_base_management_user().id):
            c += 1
            print(f"scanning users ({c}/{total_amount_of_users})")
            # -1 because the user is always matched with the base admin
            total_matches += (u.state.matches.count() - 1)

    summary_meta = json.loads(json.dumps(dict(
        chat_connections_per_user=chat_connections_per_user,
        new_user_registrations=new_user_registrations,
        amount_new_volunteers=total_volunteers,
        amount_new_learners=total_learners,
        users_called_login_api=users_called_login_api,
        users_sucessfully_logged_in=users_sucessfully_logged_in,
        users_changed_profile=users_changed_profile,
        users_logged_out=users_logged_out,
        call_rooms_authenticated=call_rooms_authenticated,
        absolute_requests_tracked=absolute_requests_tracked,
        matches_made=matches_made,
        absoulte_matches_made=len(matches_made),
        connection_disconnection_events=connection_disconnection_events,
        total_amount_of_users=total_amount_of_users,
        chat_interations_per_dialog=chat_interations_per_dialog,
        amount_dialogs_where_messages_where_send_in=len(
            list(chat_interations_per_dialog.keys())),
        # total_matches=total_matches,
        total_amount_events_processed=event_count,
        summary_for_hour=this_hour
    ), cls=CoolerJson))
    from tracking.models import Summaries

    Summaries.objects.create(
        label="hourly-event-summary",
        slug=f"hour-{this_hour}",
        rate=Summaries.RateChoices.HOURLY,
        meta=summary_meta
    )

    return summary_meta


@shared_task
def create_series(start_time=None, end_time=None, regroup_by="hour"):
    """
    Creates plottable series every hour, these can then be rendered in the stats dashboard

    We want to measure
    - the influx of users
        - [x] amount registrations
        - [x] amount registrations volunteers
        - [x] amount registrations learners
        - [x] ration of vol/learner of new registrations

    - the page activity
        - [x] amount of logins ( with expired sessions, new users, new device or was logged out )
        - [x] amount of messages send ( total amount of all messages! )
        - [x] amount of chats messages where send in ( active user conversations )
        - [x] average message amount per two user chat
        - [x] amount of video calls held
        - [x] average video call time

    - the match quality ( as mesured for a unique two user match )
        - [x] total time since last interaction
        - [x] amount of total messages
        - [x] amount of total video calls ( only counted if over 5 min mutal connection )
        - [x] average video call length
        - [x] average message amount per day with conversations

    - user specific stats
        - [x] amount of ( refugees | students | workers ) ( only counted learners! )
        - [x] amount of users prefere ( any | video | phone )
        - [x] amount of users have lang level ( 0 | 1 | 2 | 3 )
        - [x] amount of users interested in XXXX ( make total pie chart )
        - [x] amount of users per age
        - [x] average user age
        - [x] amount of users state ( only_registered | email verified | form completed | matched )
        - [x] total most available times calculated over all users

    - additions
        - [ ] fix video call amount charts
        - [ ] add match logevity chart ( logevity per matching )
        - [ ] options to request analysis of a specific match

        - total averages:
            - [ ] total average registrations per day
            - [ ] total average logins per day
            - [ ] total average messages send per day
            - [ ] total average video calls per day
    """
    # Create a graph of histogram or something from the hourly event summaries

    actions = []
    from tracking.models import Summaries
    from management import controller
    from datetime import datetime

    if start_time is None:
        first_event_logged_time = datetime(
            2022, 12, 19, 5, 18, 11, 931582)
        start_time = str(first_event_logged_time)

    if end_time is None:
        print("END TIME not set")
        end_time = str(datetime.now())

    summaries = Summaries.objects.filter(label="hourly-event-summary")
    end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S.%f')
    start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S.%f')

    start_time = start_time.replace(minute=0, second=0, microsecond=0)
    end_time = end_time.replace(minute=0, second=0, microsecond=0)

    total_user_growth = {"x": [], "y": []}

    match_slug_to_interations = {}  # Recods all interactions of matches

    def init_slug_interaction(pk1, pk2):
        if pk1 == controller.get_base_management_user().id or pk2 == controller.get_base_management_user().id:
            return None
        if pk1 < pk2:
            slug = f"{pk1}-{pk2}"
        else:
            slug = f"{pk2}-{pk1}"
        if not slug in match_slug_to_interations:
            match_slug_to_interations[slug] = []
        return slug

    time_series = {
        # all is per hour, this doesn't contain failed logins
        "logins__time_x_login_count_y": [],
        "config__logins__time_x_login_count_y": {
            "title": "Logins per Day",
            "slug": "loging_count_day",
            "combine": "sum"
        },
        "registrations__time_x_login_count_y": [],
        "config__registrations__time_x_login_count_y": {
            "title": "Registrations per Day",
            "slug": "registration_count_day",
            "combine": "sum"
        },
        "matches_made__time_x_login_count_y": [],
        "config__matches_made__time_x_login_count_y": {
            "title": "Matches made per Day",
            "slug": "matches_made_count_day",
            "combine": "sum"
        },
        "events_happened__time_x_login_count_y": [],
        "chat_messages_send__time_x_send_count_y": [],
        "amount_of_chats_messages_send__time_x_send_count_y": [],
        "users_online__time_x_online_count_y": [],
        "volunteer_registrations__time_x_vol_y": [],
        "learner_registrations__time_x_vol_y": [],
        "video_calls_held__time_x_amount_y": [],
        "average_call_length__time_x_length_y": [],
        "config__average_call_length__time_x_length_y": {
            "title": "Average call length that Day",
            "combine": "avg",
            "slug": "average_call_length_day"
        },
        "message_mount_per_user_chat__time_x_amount_y": [],
        "config__message_mount_per_user_chat__time_x_amount_y": {
            "title": "Average message amount per two user chat that Day",
            "combine": "avg",
            "slug": "average_message_amount_per_chat_day"
        },
    }

    def string_remove_timezone(time_string):
        if "+" in time_string:
            return time_string.split("+")[0]
        return time_string

    user_hash_online_map = {}

    video_room_to_users_connected = {}

    c = 0

    for sum in summaries:
        summary_time = string_remove_timezone(sum.meta['summary_for_hour'])
        summary_time = datetime.strptime(summary_time, '%Y-%m-%d %H:%M:%S')
        if not (summary_time < end_time and summary_time > start_time):
            print(f"Summary '{summary_time}' outside time range ignoring...",
                  f"end: {end_time}, start: {start_time}", summary_time < end_time, summary_time > start_time)
            continue

        c += 1
        print("TBS", sum.meta)
        if not "amount_new_volunteers" in sum.meta:
            # TODO remove
            print("deleted depricated sum format ")
            sum.delete()
            continue

        total_send_messages = 0
        time_series["logins__time_x_login_count_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": len(sum.meta["users_sucessfully_logged_in"])
        })

        time_series["volunteer_registrations__time_x_vol_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": sum.meta["amount_new_volunteers"]
        })

        len_groth = c

        if len_groth > 1:
            import math
            new_reg = abs(
                time_series["volunteer_registrations__time_x_vol_y"][len_groth - 1]["y"])
            total_user_growth["y"].append(
                total_user_growth["y"][len_groth - 2] + new_reg)
        else:
            total_user_growth["y"].append(
                time_series["volunteer_registrations__time_x_vol_y"][len_groth - 1]["y"] + 1200)
        total_user_growth["x"].append(sum.meta["summary_for_hour"])

        time_series["learner_registrations__time_x_vol_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": sum.meta["amount_new_learners"]
        })

        time_series["registrations__time_x_login_count_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": len(sum.meta["new_user_registrations"])
        })

        time_series["matches_made__time_x_login_count_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": len(sum.meta["matches_made"])
        })

        time_series["events_happened__time_x_login_count_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": sum.meta["total_amount_events_processed"]
        })

        # Then check if there are events to be added to the user action frequency map
        for hash in sum.meta["chat_connections_per_user"].keys():

            for event in sum.meta["chat_connections_per_user"][hash]["disconnected"]:
                user_hash_online_map[hash] = False

            for event in sum.meta["chat_connections_per_user"][hash]["connected"]:
                user_hash_online_map[hash] = True

            # update_user_action_fequency_map(hash, )
            total_send_messages += sum.meta["chat_connections_per_user"][hash]["send_messages_count"]

        # amount of video calls held & average duration of video call
        # TODO: we need to consider the auto video room close time ( then no disconnect event would be required )
        user_call_list = []  # All users that basicly ended an officially counted call this hour
        user_call_length_list = []
        for video_event in sum.meta["connection_disconnection_events"]:
            # TODO if not in add ...
            if not video_event["room_name"] in video_room_to_users_connected:
                video_room_to_users_connected[video_event["room_name"]] = {
                    "last_connect_time": "", "calls": []}
                video_room_to_users_connected[video_event["room_name"]]["actors"] = [
                ]

            if not video_event["actor"] in video_room_to_users_connected[video_event["room_name"]]:

                if video_event["event"] == "participant-connected":

                    video_room_to_users_connected[video_event["room_name"]
                                                  ]["last_connect_time"] = video_event["timestamp"][0]

                    actions.append({
                        "type": "disconnect-detected",
                        "event": video_event,
                    })

                    if not video_event["actor"] in video_room_to_users_connected[video_event["room_name"]]["actors"]:
                        video_room_to_users_connected[video_event["room_name"]]["actors"].append(
                            video_event["actor"])

            if len(video_room_to_users_connected[video_event["room_name"]]["actors"]) > 2:
                raise Exception("More than two users in a video room \n " +
                                str(video_room_to_users_connected[video_event["room_name"]]))

            if len(video_room_to_users_connected[video_event["room_name"]]) > 1:
                print("Multiple users where connected")
                if video_event["event"] == "participant-disconnected":
                    # If more than two users where connected and one user disconnected a session just ended
                    print("EVENT", video_event)
                    print("DT", datetime.strptime(
                        video_event['timestamp'][0], '%Y-%m-%dT%H:%M:%S.%fZ'))

                    try:
                        duration = datetime.strptime(video_event["timestamp"][0], '%Y-%m-%dT%H:%M:%S.%fZ') - datetime.strptime(
                            video_room_to_users_connected[video_event["room_name"]]["last_connect_time"], '%Y-%m-%dT%H:%M:%S.%fZ')
                    except:
                        duration = "error_unknown"
                        print("ERROR couldnt calculate duration")
                    video_room_to_users_connected[video_event["room_name"]]["calls"].append({
                        "duration": str(duration),
                        "start_time": video_room_to_users_connected[video_event["room_name"]]["last_connect_time"],
                        "end_time": video_event["timestamp"][0]
                    })

                    if not isinstance(duration, str):
                        if duration.total_seconds() > 180:
                            user_call_list.append(video_event["actor"])
                            user_call_length_list.append(duration)

                            from management.models import Room

                            users = []
                            import itertools

                            for u_hash in video_room_to_users_connected[video_event["room_name"]]["actors"]:
                                try:
                                    users.append(
                                        controller.get_user_by_hash(u_hash))
                                except:
                                    pass
                            match_combos = list(
                                itertools.combinations(users, 2))

                            for combo in match_combos:
                                slug = init_slug_interaction(
                                    combo[0].pk, combo[1].pk)
                                if not slug is None:
                                    match_slug_to_interations[slug].append({
                                        "kind": "video_call",
                                        "duration": duration.total_seconds(),
                                        "time": video_event["timestamp"][0]
                                    })

                            # The check of disconnect event should be last since we first detect disconnect for 2 users and update the time in call duration
            if not video_event["actor"] in video_room_to_users_connected[video_event["room_name"]]:

                if video_event["event"] == "participant-disconnected":
                    print("DICONNECTED", video_event)
                    print(
                        "CONN", video_room_to_users_connected[video_event["room_name"]]["actors"])

                    if video_event["actor"] in video_room_to_users_connected[video_event["room_name"]]["actors"]:
                        video_room_to_users_connected[video_event["room_name"]]["actors"].remove(
                            video_event["actor"])
                    else:
                        print("Dissconeect eventhough not registered",
                              video_event, video_event["actor"])

        print("TBS: ", user_call_length_list)
        if len(user_call_length_list) > 0:
            average_call_length = reduce(
                operator.add, [s.total_seconds() / 60.0 for s in user_call_length_list]) / float(len(user_call_length_list))
        else:
            average_call_length = 0.0

        time_series["average_call_length__time_x_length_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": average_call_length
        })

        # Now we can calulucate the amount of video calls that have been held
        # We only count a call if it was over 5 min
        time_series["video_calls_held__time_x_amount_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": len(user_call_list)
        })

        time_series["amount_of_chats_messages_send__time_x_send_count_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": int(sum.meta["amount_dialogs_where_messages_where_send_in"])
        })

        for dia_slug in sum.meta["chat_interations_per_dialog"]:
            pk1, pk2 = [int(x) for x in dia_slug.split("-")]
            slug = init_slug_interaction(pk1, pk2)
            if slug is not None:
                for msgs in sum.meta["chat_interations_per_dialog"][dia_slug]["msgs"]:
                    match_slug_to_interations[slug].append({
                        "kind": "chat_interaction",
                        "data": msgs,
                        "time": msgs["time"]
                    })

        interations = [int(sum.meta["chat_interations_per_dialog"][s]["amnt_msgs_send"])
                       for s in sum.meta["chat_interations_per_dialog"]]
        average_messages_send_per_chat = 0
        for inter in interations:
            print("INTER", inter)
            average_messages_send_per_chat += inter

        if len(interations) > 0:
            average_messages_send_per_chat = float(
                average_messages_send_per_chat) / float(len(interations))
        else:
            average_messages_send_per_chat = 0.0

        print("TBS AVG", average_messages_send_per_chat)
        time_series["message_mount_per_user_chat__time_x_amount_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": average_messages_send_per_chat
        })

        time_series["chat_messages_send__time_x_send_count_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": total_send_messages
        })

        time_series["users_online__time_x_online_count_y"].append({
            "x": sum.meta["summary_for_hour"],
            "y": len([user_hash_online_map[u] for u in user_hash_online_map if user_hash_online_map[u] == True])
        })

    # Now we convert this into format for 'chartjs'
    # https://www.chartjs.org/docs/latest/samples/information.html
    # also pretty nice: https://github.com/plotly/plotly.js/
    if regroup_by == "hour":
        # then there is nothing todo, perdefault it is grouped by hour
        pass
    elif regroup_by == "day":
        updated_series = {}
        time_buckets = {}

        original_time_series = time_series.copy()
        time_series = {k: time_series[k]
                       for k in time_series if not k.startswith("config__")}

        for k in time_series:

            config = {
                "title": k,
                "combine": "sum"
            }

            if f"config__{k}" in original_time_series:
                config = original_time_series[f"config__{k}"]
            updated_series[k] = []
            time_buckets[k] = {}
            for elem in time_series[k]:
                time = datetime.strptime(string_remove_timezone(
                    elem["x"]), '%Y-%m-%d %H:%M:%S')
                time = str(time.replace(
                    hour=0, minute=0, second=0, microsecond=0))

                if not time in time_buckets[k]:
                    if config["combine"] == "sum":
                        time_buckets[k][time] = elem["y"]
                    elif config["combine"] == "avg":
                        time_buckets[k][time] = [elem["y"]]
                else:
                    if config["combine"] == "sum":
                        time_buckets[k][time] += elem["y"]
                    elif config["combine"] == "avg":
                        time_buckets[k][time].append(elem["y"])

        for k in time_buckets:

            if f"config__{k}" in original_time_series:
                if original_time_series[f"config__{k}"]["combine"] == "avg":
                    for time in time_buckets[k]:
                        times = [b for b in time_buckets[k][time] if b != 0.0]
                        if len(times) > 0:
                            time_buckets[k][time] = float(
                                reduce(operator.add, times)) / float(len(times))
                        else:
                            time_buckets[k][time] = 0.0

            for time in time_buckets[k]:
                updated_series[k].append({
                    "y": time_buckets[k][time],
                    "x": time
                })
        time_series = updated_series

    # Now generate some per-match basis metrics
    match_slug_to_metrics = {}
    match_activity_buckets = {}
    match_interaction_amount_distribution = {}
    for match_slug in match_slug_to_interations:

        # sort match_slug_to_interations[match_slug] by time
        total_chat_ineractions = 0
        total_video_call_interactions = 0
        video_call_interaction_durations = []
        last_chat_interaction_time = None
        inbetween_chat_interactions_time = []
        last_video_call_interaction_time = None
        inbetween_video_call_interactions_time = []

        last_any_interaction_time = None

        ineractions = sorted(
            match_slug_to_interations[match_slug], key=lambda k: k['time'])

        match_interaction_amount_distribution[match_slug] = len(ineractions)

        oldest_interaction_time = None
        newest_interaction_time = None

        for interaction in match_slug_to_interations[match_slug]:

            print("TBS interaction", interaction)
            # How can I parse this datetime string in python '2022-12-19 05:55:55.903839+00:00'
            # https://stackoverflow.com/questions/466345/converting-string-into-datetime
            if interaction["kind"] == "chat_interaction":
                total_chat_ineractions += 1
                if last_chat_interaction_time is not None:
                    inbetween_chat_interactions_time.append(
                        (datetime.strptime(interaction["time"], '%Y-%m-%d %H:%M:%S.%f+00:00') - last_chat_interaction_time).total_seconds() / (60.0))
                last_chat_interaction_time = datetime.strptime(
                    interaction["time"], '%Y-%m-%d %H:%M:%S.%f+00:00')
                last_any_interaction_time = datetime.strptime(
                    interaction["time"], '%Y-%m-%d %H:%M:%S.%f+00:00')
            elif interaction["kind"] == "video_call":

                total_video_call_interactions += 1
                video_call_interaction_durations.append(
                    interaction["duration"])
                if last_video_call_interaction_time is not None:
                    inbetween_video_call_interactions_time.append((datetime.strptime(
                        interaction["time"], '%Y-%m-%dT%H:%M:%S.%fZ') - last_video_call_interaction_time).total_seconds() / (60.0 * 60.0))
                last_video_call_interaction_time = datetime.strptime(
                    interaction["time"],  '%Y-%m-%dT%H:%M:%S.%fZ')

                last_any_interaction_time = datetime.strptime(
                    interaction["time"], '%Y-%m-%dT%H:%M:%S.%fZ')

            if oldest_interaction_time is None or last_any_interaction_time < oldest_interaction_time:
                oldest_interaction_time = last_any_interaction_time

            if newest_interaction_time is None or last_any_interaction_time > newest_interaction_time:
                newest_interaction_time = last_any_interaction_time

        # Total time since the last interaction in hours
        time_since_last_interaction = (
            datetime.now() - last_any_interaction_time).total_seconds() / (60.0 * 60.0)

        current_match_activity = "undefined"
        if time_since_last_interaction > 24.0 * 14.0:
            current_match_activity = "over_2_weeks_since_last_interaction"
        elif time_since_last_interaction > 24.0 * 7.0:
            current_match_activity = "over_1_week_since_last_interaction"
        elif time_since_last_interaction > 24.0 * 2.0:
            current_match_activity = "over_2_days_since_last_interaction"
        elif time_since_last_interaction > 24.0:
            current_match_activity = "over_1_day_since_last_interaction"
        else:
            current_match_activity = "active_within_last_day"

        if not current_match_activity in match_activity_buckets:
            match_activity_buckets[current_match_activity] = 0
        match_activity_buckets[current_match_activity] += 1

        total_interaction_logevity = None
        if oldest_interaction_time is None or newest_interaction_time is None:
            total_interaction_logevity = newest_interaction_time - oldest_interaction_time

        match_slug_to_metrics[match_slug] = {
            "oldest_interaction_time": oldest_interaction_time,
            "newest_interaction_time": newest_interaction_time,
            "total_interaction_logevity": total_interaction_logevity,
            "total_chat_ineractions": total_chat_ineractions,
            "total_video_call_interactions": total_video_call_interactions,
            "total_time_since_last_interaction": time_since_last_interaction,
            "match_activity": current_match_activity,
            "total_interaction_amount": len(ineractions),
            "average_video_call_duration": float(reduce(operator.add, video_call_interaction_durations)) / float(len(video_call_interaction_durations)) if len(video_call_interaction_durations) > 0 else 0.0,
            "average_time_between_chat_interactions": float(reduce(operator.add, inbetween_chat_interactions_time)) / float(len(inbetween_chat_interactions_time)) if len(inbetween_chat_interactions_time) > 0 else 0.0,
            "average_time_between_video_call_interactions": float(reduce(operator.add, inbetween_video_call_interactions_time)) / float(len(inbetween_video_call_interactions_time)) if len(inbetween_video_call_interactions_time) > 0 else 0.0,
        }

    current_match_activity_title_mappings = {
        "over_2_weeks_since_last_interaction": "Over 2 weeks since last interaction",
        "over_1_week_since_last_interaction": "Last interaction over 1 week ago",
        "over_2_days_since_last_interaction": "Last interaction over 2 days ago",
        "over_1_day_since_last_interaction": "Last interaction yesterday",
        "active_within_last_day": "Active within last 24 hours"
    }

    # Now we do some caluclations to estimate the match quality
    # total_messages_send = 1 === "less-than-1-messages-send", "min-5-messages-send", "min-10-messages-send", "over-20-messages-send"
    # total_video_calls = 1 === "no-videocalls", "min-1-video-calls", "min-10-video-calls", "over-20-video-calls"
    # average_video_call_duration === "under-5min-average"

    match_chat_quality_name_mapping = {
        "no-messages-send": "Never comunicated",
        "at-least-1-messages-send": "Only one message send",
        "more-than-1-messages-send": "More than one message send",
        "min-5-messages-send": "At least 5 messages send",
        "min-10-messages-send": "At least 10 messages send",
        "over-20-messages-send": "Twenty or more messages send"
    }

    match_quality_estimation = {
        "chat": {
            "no-messages-send": 0,
            "at-least-1-messages-send": 0,
            "more-than-1-messages-send": 0,
            "min-5-messages-send": 0,
            "min-10-messages-send": 0,
            "over-20-messages-send": 0
        },
        "video_call": {
            "no-videocalls": 0,
            "min-1-video-calls": 0,
            "min-2-video-calls": 0,
            "min-3-video-calls": 0,
            "over-5-video-calls": 0
        }
    }
    for match_slug in match_slug_to_metrics:
        if match_slug_to_metrics[match_slug]["total_chat_ineractions"] < 1:
            match_quality_estimation["chat"]["no-messages-send"] += 1
        elif match_slug_to_metrics[match_slug]["total_chat_ineractions"] >= 20:
            match_quality_estimation["chat"]["over-20-messages-send"] += 1
        elif match_slug_to_metrics[match_slug]["total_chat_ineractions"] >= 10:
            match_quality_estimation["chat"]["min-10-messages-send"] += 1
        elif match_slug_to_metrics[match_slug]["total_chat_ineractions"] >= 5:
            match_quality_estimation["chat"]["min-5-messages-send"] += 1
        elif match_slug_to_metrics[match_slug]["total_chat_ineractions"] >= 1:
            match_quality_estimation["chat"]["at-least-1-messages-send"] += 1

        # Write the if else chanin for filling the 'video_call' part of the match_quality_estimation dict
        if match_slug_to_metrics[match_slug]["total_video_call_interactions"] < 1:
            match_quality_estimation["video_call"]["no-videocalls"] += 1
        elif match_slug_to_metrics[match_slug]["total_video_call_interactions"] >= 5:
            match_quality_estimation["video_call"]["over-5-video-calls"] += 1
        elif match_slug_to_metrics[match_slug]["total_video_call_interactions"] >= 3:
            match_quality_estimation["video_call"]["min-3-video-calls"] += 1
        elif match_slug_to_metrics[match_slug]["total_video_call_interactions"] >= 2:
            match_quality_estimation["video_call"]["min-2-video-calls"] += 1
        elif match_slug_to_metrics[match_slug]["total_video_call_interactions"] >= 1:
            match_quality_estimation["video_call"]["min-1-video-calls"] += 1

    # Total average match quality estimation
    # 1 - total average video duration
    # 2 - total average video calls per match
    # 3 - total average messages per match
    # 4 - total average time between video calls
    # 4 - total average time between video messages
    total_average_estimations = {
        "video_duration": [],
        "video_calls_per_match": [],
        "messages_per_match": [],
        "time_between_video_calls": [],
        "time_between_messages": [],
        "total_match_interactions": []  # TODO use
    }

    for match_slug in match_slug_to_metrics:
        total_average_estimations["video_duration"].append(
            match_slug_to_metrics[match_slug]["average_video_call_duration"])

        total_average_estimations["video_calls_per_match"].append(
            match_slug_to_metrics[match_slug]["total_video_call_interactions"])

        total_average_estimations["messages_per_match"].append(
            match_slug_to_metrics[match_slug]["total_chat_ineractions"])

        total_average_estimations["time_between_video_calls"].append(
            match_slug_to_metrics[match_slug]["average_time_between_video_call_interactions"])

        total_average_estimations["time_between_messages"].append(
            match_slug_to_metrics[match_slug]["average_time_between_chat_interactions"])

        total_average_estimations["total_match_interactions"].append(
            match_slug_to_interations[match_slug]["total_interaction_amount"])

    total_average_estimations_uncalculated = total_average_estimations.copy()

    for key in total_average_estimations:
        total_average_estimations[key] = float(reduce(
            operator.add, total_average_estimations[key])) / float(len(total_average_estimations[key])) if len(total_average_estimations[key]) > 0 else 0.0

    print("TBS: new total_average_estimations", total_average_estimations)

    match_interaction_amount_distribution = dict(
        sorted(match_interaction_amount_distribution.items(), key=lambda x: x[1]))

    from tracking.models import GraphModel

    combined_graphs = []
    all_slugs = []

    def create_graph_model_and_store(slug, graph_data):
        all_slugs.append(slug)
        GraphModel.objects.create(
            slug=slug,
            graph_data=graph_data
        )
        combined_graphs.append(graph_data)

    create_graph_model_and_store("total_user_growth", {
        "data": [{
            "x": total_user_growth["x"],
            "y": total_user_growth["y"],
            "type": "bar"
        }],
        "layout": {
            "title": "Total User Groth",
        }
    })

    create_graph_model_and_store("overall_match_quality_stats", {
        "data": [{
            "x": [k for k in total_average_estimations],
            "y": [total_average_estimations[k] for k in total_average_estimations],
            "type": "bar"
        }],
        "layout": {
            "title": "Absoulate match interation measures",
        }
    })

    create_graph_model_and_store("per_match_activity", {
        "data": [{
            "values": [match_activity_buckets[k] for k in match_activity_buckets],
            "labels": [current_match_activity_title_mappings[k] for k in match_activity_buckets],
            "type": "pie"
        }],
        "layout": {
            "title": "Match activity",
        }
    })

    create_graph_model_and_store("per_match_interactions", {
        "data": [{
            "y": [match_interaction_amount_distribution[k] for k in match_interaction_amount_distribution],
            "x": [k for k in match_interaction_amount_distribution],
            "type": "bar"
        }],
        "layout": {
            "title": "match to interaction amount distribution",
        }
    })

    create_graph_model_and_store("chat_quality_per_match", {
        "data": [{
            "values": [match_quality_estimation["chat"][estimate] for estimate in match_quality_estimation["chat"]],
            "labels": [match_chat_quality_name_mapping[k] for k in match_quality_estimation["chat"]],
            "type": "pie"
        }],
        "layout": {
            "title": "Chat interactions per matching",
        }
    })

    create_graph_model_and_store("video_call_quality_per_match", {
        "data": [{
            "values": [match_quality_estimation["video_call"][estimate] for estimate in match_quality_estimation["video_call"]],
            "labels": [k for k in match_quality_estimation["video_call"]],
            "type": "pie"
        }],
        "layout": {
            "title": "Match Video call quality estimation",
        }
    })

    create_graph_model_and_store("chat_and_vieo_interactions_per_match", {
        "data": [
            {
                "x": [slug for slug in match_slug_to_metrics],
                "y": [match_slug_to_metrics[slug]["total_video_call_interactions"] for slug in match_slug_to_metrics],
                "type": "bar",
                "name": "Total video call interactions"
            },
            {
                "x": [slug for slug in match_slug_to_metrics],
                "y": [match_slug_to_metrics[slug]["total_chat_ineractions"] for slug in match_slug_to_metrics],
                "type": "bar",
                "name": "Total chat interactions"
            }
        ],
        "layout": {
            "title": "Interactions per matching",
            "showlegend": True
        }
    })

    create_graph_model_and_store("lerner_vs_volunteer_registrations", {
        "data": [
            {
                "x": [x["x"] for x in time_series["learner_registrations__time_x_vol_y"]],
                "y": [y["y"] for y in time_series["learner_registrations__time_x_vol_y"]],
                "type": "bar",
                "name": "Learners registered"
            },
            {
                "x": [x["x"] for x in time_series["volunteer_registrations__time_x_vol_y"]],
                "y": [y["y"] for y in time_series["volunteer_registrations__time_x_vol_y"]],
                "type": "bar",
                "name": "Volunteers registered"
            }
        ],
        "layout": {
            "title": "Learner vs Volunteer registrations",
            "showlegend": True
        }
    })

    create_graph_model_and_store("learner_vs_volunteers_vs_total_registrations", {
        "data": [
            {
                "x": [x["x"] for x in time_series["registrations__time_x_login_count_y"]],
                "y": [y["y"] for y in time_series["registrations__time_x_login_count_y"]],
                "type": "bar",
                "name": "Total registrations"
            },
            {
                "x": [x["x"] for x in time_series["learner_registrations__time_x_vol_y"]],
                "y": [y["y"] for y in time_series["learner_registrations__time_x_vol_y"]],
                "type": "bar",
                "name": "Learners registered"
            },
            {
                "x": [x["x"] for x in time_series["volunteer_registrations__time_x_vol_y"]],
                "y": [y["y"] for y in time_series["volunteer_registrations__time_x_vol_y"]],
                "type": "bar",
                "name": "Volunteers registered"
            },
        ],
        "layout": {
            "title": "Learner vs Volunteer vs Total registrations",
            "barmode": "overlay",
            "showlegend": True
        }
    })

    # TODO: we still need to update all the time series

    data = {
        "time_series": time_series,
        "total_average_estimations": total_average_estimations,
        "total_average_estimations_uncalculated": total_average_estimations_uncalculated,
        "extra": {
            "video_room_to_users_connected": video_room_to_users_connected,
            "match_slug_to_interations": match_slug_to_interations,
            "match_slug_to_metrics": match_slug_to_metrics
        },
        "actions": actions,
        "combined": combined_graphs
    }

    # But only the ones that have a slug assigned in their config
    # Also store the time series as graphes!
    for series in original_time_series:
        if series.startswith("config__"):
            if 'slug' in original_time_series[series]:
                series_name = series.replace("config__", "")
                all_slugs.append(original_time_series[series]['slug'])
                GraphModel.objects.create(
                    slug=original_time_series[series]['slug'],
                    graph_data={
                        "data": [
                            {
                                "x": [x["x"] for x in time_series[series_name]],
                                "y": [y["y"] for y in time_series[series_name]],
                                "type": "bar",  # Time series charts are per default always bar
                                "name": original_time_series[series]['title']
                            },
                        ],
                        "layout": {
                            "title": original_time_series[series]['title'],
                        }
                    }
                )

    Summaries.objects.create(
        label=f"time-series-summary-{regroup_by}",
        slug=f"start-{start_time}-{end_time}".replace(" ", "-"),
        rate=Summaries.RateChoices.HOURLY,
        meta=data
    )

    Summaries.objects.create(
        label=f"series-graph-summary-{regroup_by}",
        slug=f"start-{start_time}-{end_time}".replace(" ", "-"),
        rate=Summaries.RateChoices.HOURLY,
        meta={
            "slugs": all_slugs
        }
    )

    return data


@ shared_task
def collect_static_stats():
    from management import controller
    from management.models import Profile, State
    from tracking.models import Summaries
    from datetime import datetime

    total_amount_of_users = User.objects.count()
    amount_of_volunteer = 0
    amount_of_learners = 0
    total_matches = 0

    lerner_group_kind = {
        Profile.normalize_choice(Profile.TargetGroupChoices.REFUGEE_LER): 0,
        Profile.normalize_choice(Profile.TargetGroupChoices.STUDENT_LER): 0,
        Profile.normalize_choice(Profile.TargetGroupChoices.WORKER_LER): 0,
        Profile.normalize_choice(Profile.TargetGroupChoices.ANY_LER): 0,
        "total": 0
    }

    total_user_state_stats = {
        "only_registered": 0,
        "email_verified": 0,
        "form_completed": 0,
        "matched": 0
    }

    total_prefered_call_medium = {
        str(choice[0]): 0 for choice in Profile.SpeechMediumChoices.choices
    }
    total_prefered_call_medium["total"] = 0
    print("total_prefered_call_medium", total_prefered_call_medium)

    total_user_interest_state = {
        str(choice[0]): 0 for choice in Profile.InterestChoices.choices
    }
    total_user_interest_state.update({
        "total_users_counted": 0,
        "total_choices_counted": 0
    })

    learner_lang_level_stats = {
        str(choice[0]): 0 for choice in Profile.LanguageLevelChoices.choices
    }
    learner_lang_level_stats["total"] = 0

    age_buckets = {}
    cur_year = int(datetime.now().year)

    availability_buckets = {}
    total_availabilities_counted = 0

    absolute_user_groth_by_day = {}

    total_idividual_matches = set()
    c = 0
    for u in User.objects.exclude(id=controller.get_base_management_user().id):
        c += 1
        print(f"scanning users ({c}/{total_amount_of_users})")
        if u.profile.user_type == "volunteer":
            amount_of_volunteer += 1
        else:
            # Learners
            if u.state.user_form_state == State.UserFormStateChoices.FILLED:
                lerner_group_kind[Profile.normalize_choice(
                    u.profile.target_group)] += 1
                lerner_group_kind["total"] += 1

                learner_lang_level_stats[u.profile.lang_level] += 1
                learner_lang_level_stats["total"] += 1

            amount_of_learners += 1
        # -1 because the user is always matched with the base admin
        total_matches += (u.state.matches.count() - 1)

        ums = u.state.matches.all()
        for o_usr in ums:
            pk1, pk2 = int(u.pk), int(o_usr.pk)
            if pk1 < pk2:
                match_slug = f"{pk1}-{pk2}"
            else:
                match_slug = f"{pk1}-{pk2}"
            if not (controller.get_base_management_user().id == pk1 or
                    controller.get_base_management_user().id == pk2):
                total_idividual_matches.add(match_slug)

        if u.state.matches.count() > 1:
            total_user_state_stats["matched"] += 1
        elif u.state.user_form_state == State.UserFormStateChoices.FILLED:
            total_user_state_stats["form_completed"] += 1
        elif u.state.email_authenticated:
            total_user_state_stats["email_verified"] += 1
        else:
            total_user_state_stats["only_registered"] += 1

        if u.state.user_form_state == State.UserFormStateChoices.FILLED:
            for interest in u.profile.interests:
                total_user_interest_state[interest] += 1
                total_user_interest_state["total_choices_counted"] += 1
            total_user_interest_state["total_users_counted"] += 1

            total_prefered_call_medium[u.profile.speech_medium]

            total_prefered_call_medium["total"] += 1

            from management.validators import DAYS

            user_availability = u.profile.availability
            for day in user_availability:
                for slot in user_availability[day]:
                    slug = f"{day}_{slot}"
                    if slug not in availability_buckets:
                        availability_buckets[slug] = 0
                    availability_buckets[slug] += 1
                    total_availabilities_counted += 1

                # Organize age bucked by bukketing the years

        usr_age = str(cur_year - int(u.profile.birth_year))
        if usr_age not in age_buckets:
            age_buckets[usr_age] = 0
        age_buckets[usr_age] += 1

        #
        registration_day_normalized = str(u.date_joined.replace(
            hour=0, minute=0, second=0, microsecond=0))
        if not registration_day_normalized in absolute_user_groth_by_day:
            absolute_user_groth_by_day[registration_day_normalized] = 0
        absolute_user_groth_by_day[registration_day_normalized] += 1

    amount_inidividual_matches = len(total_idividual_matches)
    print('TBS', amount_inidividual_matches, total_idividual_matches)

    # calculate the avarage user age:
    total_age_sum = 0
    total_ages_counted = 0
    for a in age_buckets:
        total_age_sum += int(a) * age_buckets[a]
        total_ages_counted += age_buckets[a]

    average_age = float(total_age_sum) / float(total_ages_counted)

    from tracking.models import GraphModel

    combined_graphs = []
    combined_tables = []
    all_slugs = []

    def create_graph_model_and_store(slug, graph_data, type="plot"):
        all_slugs.append(slug)
        GraphModel.objects.create(
            slug=slug,
            graph_data=graph_data,
            type=type
        )
        if type == "plot":
            combined_graphs.append(graph_data)
        elif type == "table":
            combined_tables.append(graph_data)

    create_graph_model_and_store("group_kind_for_learners", {
        "data": [{
            "values": [lerner_group_kind[kind] for kind in lerner_group_kind if kind != "total"],
            "labels": [kind for kind in lerner_group_kind if kind != "total"],
            "type": "pie"
        }],
        "layout": {
            "title": "Group kind for learners"
        }
    })

    create_graph_model_and_store("absolute_user_groth_by_day", {
        "data": [{
            "x": [k for k in absolute_user_groth_by_day],
            "y": [absolute_user_groth_by_day[k] for k in absolute_user_groth_by_day],
            "type": "bar"
        }],
        "layout": {
            "title": "Absolute user groth, per day since launch"
        }
    })

    create_graph_model_and_store("user_age_distribution", {
        "data": [{
            "x": [kind for kind in age_buckets if kind != "total"],
            "y": [age_buckets[kind] for kind in age_buckets if kind != "total"],
            "type": "bar"
        }],
        "layout": {
            "title": "User age distribution"
        }
    })

    create_graph_model_and_store("learner_language_level_pie", {
        "data": [{
            "values": [learner_lang_level_stats[kind] for kind in learner_lang_level_stats if kind != "total"],
            "labels": [kind for kind in learner_lang_level_stats if kind != "total"],
            "type": "pie"
        }],
        "layout": {
            "title": "Learner language level"
        }
    })

    create_graph_model_and_store("user_commitment_state_pie", {
        "data": [{
            "values": [total_user_state_stats[state] for state in total_user_state_stats],
            "labels": [state for state in total_user_state_stats],
            "type": "pie"
        }],
        "layout": {
            "title": "User state chart"
        }
    })

    create_graph_model_and_store("user_interests_pie", {
        "data": [{
            "values": [total_user_interest_state[state] for state in total_user_interest_state if not state.startswith("total")],
            "labels": [state for state in total_user_interest_state if not state.startswith("total")],
            "type": "pie"
        }],
        "layout": {
            "title": "User interests chart"
        }
    })

    create_graph_model_and_store("total_values_table", {
        "headers": ["Total amount of users", "Total amount of matches", "Total amount of individual matches", "Total amount of volunteers", "Total amount of learners"],
        "rows": [
            [total_amount_of_users, total_matches, amount_inidividual_matches,
                amount_of_volunteer, amount_of_learners]
        ]
    }, type="table")

    data = {
        "total_amoount_of_users": total_amount_of_users,
        "total_matches": total_matches,
        "total_individual_matches": amount_inidividual_matches,
        "total_amount_of_volunteers": amount_of_volunteer,
        "total_amount_of_learners": amount_of_learners,
        "total_user_state_stats": total_user_state_stats,
        "total_user_interest_state": total_user_interest_state,
        "age_buckets": age_buckets,
        "average_age": average_age,
        "total_availabily_stats": {
            "buckets": availability_buckets,
            "total": total_availabilities_counted
        },
        "prefered_call_medium": total_prefered_call_medium,
        "learner_lang_level_stat": learner_lang_level_stats,
        "charts": combined_graphs,
    }

    Summaries.objects.create(
        label="static-stats-summary",
        slug="simple-static",
        rate=Summaries.RateChoices.HOURLY,
        meta=data
    )

    return data


@ shared_task
def collect_match_quality_stats():
    """
    Some general statistics of the quality of matches
    The relevant data is collected in the hourly event summaries

    What we collect is 'interactions_by_match_slug' this records the following interactions
    - amount video calls held
    - amount chat messages send
    - time since last chat message send
    - time since last video call
    - time since matched
    - average time between video calls

    """
    pass


@ shared_task
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


@ shared_task
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
