from .models import User
import datetime
from django.utils.translation import pgettext_lazy
from .models.community_events import CommunityEvent, CommunityEventSerializer
from .models.backend_state import BackendState
from cookie_consent.models import CookieGroup, Cookie
from celery import shared_task
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
        return

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
def calculate_directional_matching_score_background(usr):
    """
    This is the backend task for calculating a matching score. 
    This will *automaticly* be executed everytime a users changes his user form
    run with calculate_directional_matching_score_background.delay(usr)
    """

    for other_usr in User.objects.all().exclude(usr=usr):
        # We do loop over all users, but for most users the score calculation will abort quickly
        # e.g.: if the user is a volunteer and the 'other_usr' is also a volunteer
        # then the score calculation would abbort imediately and return 'matchable = False'
        pass
