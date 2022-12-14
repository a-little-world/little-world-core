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
    # TODO: there is still a second event missing


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
            "gtag('config', 'AW-10994486925');\n"
            # TODO: there was another gtag I should include
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
    # TODO: add default interests
    # TODO: upload default image!
    usr.profile.save()
    return "sucessfully filled base management user profile"


@shared_task
def calculate_directional_matching_score_background(usr_hash):
    """
    This is the backend task for calculating a matching score.
    This will *automaticly* be executed everytime a users changes his user form
    run with calculate_directional_matching_score_background.delay(usr)
    """
    print(f"Calculating score for {usr_hash}")
    from .controller import get_user_by_hash
    from .matching.matching_score import calculate_directional_score_write_results_to_db

    usr = get_user_by_hash(usr_hash)
    all_other_users = User.objects.all().exclude(id=usr.id)
    print("OTHERS", all_other_users)
    for other_usr in all_other_users:
        print(f"Calculating score {usr} -> {other_usr}")
        calculate_directional_score_write_results_to_db(
            usr, other_usr, return_on_nomatch=False,
            catch_exceptions=True)
        print(f"Calculating score {other_usr} -> {usr}")
        calculate_directional_score_write_results_to_db(
            other_usr, usr, return_on_nomatch=False,
            catch_exceptions=True)


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
        LANGUAGE_LEVEL_SCORES
    )

    ScoreTableSource.objects.create(
        target_group_scores=TARGET_GROUP_SCORES,
        target_group_messages=TARGET_GROUP_MESSAGES,
        partner_location_scores=PARTNER_LOCATION_SCORES,
        language_level_scores=LANGUAGE_LEVEL_SCORES,
        # Per default select **all** scoring functions
        function_scoring_selection=list(SCORING_FUNCTIONS.keys())
    )
    return "default score source created"


@shared_task
def dispatch_track_chat_channel_event(
    message_type: str,  # connected | disconnected | message-send
    usr_hash: str,
    meta: dict
):
    """
    Automaticly triggered by some event in management.app.chat
    """
    from .controller import get_user_by_hash
    caller = "anonymous"
    try:
        caller = get_user_by_hash(usr_hash)
    except:
        print("Could not find user by hash", usr_hash)

    inline_track_event(
        caller=caller,  # TODO actually inline track supports passing users
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
def write_hourly_backend_event_summary():
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
    from datetime import timedelta
    from django.utils import timezone

    # For that fist we extract all event within that hour
    this_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    one_hour_later = this_hour + timedelta(hours=4)
    earlier = this_hour - timedelta(hours=4)
    events = Event.objects.filter(time__range=(this_hour, one_hour_later))

    chat_connected_users_per_user_time = {}
    chat_per_user_message_send_count = {}
    for event in events:
        #print("TIME", event.time)
        has_event_tags = hasattr(
            event, "tags") and isinstance(event.tags, list)
        has_caller_annotation = hasattr(event, "caller")

        #print("TAGS", event.tags)
        #print("DATA", event.metadata)

        if has_event_tags and has_caller_annotation:
            assert isinstance(event.tags, list)
            if all([x in event.tags for x in ['chat', 'channels', 'connected']]):
                # User connected to chat
                chat_connected_users_per_user_time.get(event.caller, None)
                chat_connected_users_per_user_time[event.caller] = event.time
                print("Detected user connected to chat",
                      event.caller, event.time)
            if all([x in event.tags for x in ['chat', 'channels', 'disconnected']]):
                # User connected to chat
                chat_connected_users_per_user_time[event.caller] = event.time
                print("Detected user disconnected to chat",
                      event.caller, event.time)
            if all([x in event.tags for x in ['chat', 'channels', 'message-send']]):
                if not event.caller in chat_per_user_message_send_count:
                    chat_per_user_message_send_count[event.caller] = 0
                chat_per_user_message_send_count[event.caller] += 1
                print("Detected user send message to chat",
                      event.caller, event.time)
