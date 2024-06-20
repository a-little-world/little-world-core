from datetime import datetime, timedelta, timezone
from cookie_consent.models import CookieGroup, Cookie
from celery import shared_task
from tracking.utils import inline_track_event
from dataclasses import dataclass
from management.models.user import User
import json
from management.models.community_events import CommunityEvent, CommunityEventSerializer
from management.models.backend_state import BackendState
import operator
from functools import reduce
from tracking.models import Summaries, Event
from management.models.user import User
from translations import get_translation
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
        title=get_translation("de", "community_event.coffe_break"),
        description="Zusammenkommen der Community – lerne das Team hinter Little World und andere Nutzer:innen bei einer gemütlichen Tasse Kaffee oder Tee kennen.",
        time=datetime(2022, 11, 29, 12, 00, 00,
                               00, timezone.utc),
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
    return "sucessfully filled base management user profile"

@shared_task
def send_new_message_notifications():
    from management.models.user import User
    from chat.models import Message
    from django.conf import settings
    from emails import mails
    
    # 1 - get all unitified messages
    unnotified_messages_unread = Message.objects.filter(
        recipient_notified=False,
        read=False
    ).values_list("recipient", flat=True)
    
    unnotified_messages_read = Message.objects.filter(
        recipient_notified=False,
        read=True
    ).update(
        recipient_notified=True
    )
    
    
    # 4 - send notifications to users
    send_emails = not (settings.IS_STAGE or settings.IS_DEV)
    if send_emails:
        users = User.objects.filter(id__in=unnotified_messages_unread).distinct()
        for u in users:
            u.send_email(
                subject="Neue Nachricht(en) auf Little World",
                mail_data=mails.get_mail_data_by_name("new_messages"),
                mail_params=mails.NewUreadMessagesParams(
                    first_name=u.profile.first_name,
                )
            )
        user_ids = list(users.values_list('id', flat=True))
        unnotified_messages_unread.update(recipient_notified=True)

        return {
            "sent_emails": len(user_ids),
            "user_ids": user_ids
        }

@shared_task
def fill_base_management_user_tim_profile():
    if BackendState.is_base_management_user_profile_filled(set_true=True):
        return  # Allready filled base management user profile

    from .controller import get_base_management_user

    base_management_user_description = """
Hello there 👋🏼

Im the co-founder and CTO of little world. And as of today I'm your support match!
We are currently working hard to improve our matching process and give to offer you the best experience possible.

Feel free to send me any question or suggestions.
I'll take the time to answer all your messages but I might take a little time to do so.
"""
    usr = get_base_management_user()
    usr.profile.birth_year = 1999
    usr.profile.postal_code = 52064
    usr.profile.description = base_management_user_description
    usr.profile.add_profile_picture_from_local_path(
        '/back/dev_test_data/tim_schupp_base_management_profile_new.jpeg')
    
    from management.models.state import State
    
    usr.state.extra_user_permissions.append(State.ExtraUserPermissionChoices.MATCHING_USER)
    usr.state.save()
    usr.profile.save()


@shared_task
def check_prematch_email_reminders_and_expirations():
    """
    Reoccuring task to check for email reminders that should be send out
    also check if there are expired unconfirmed_matches
    """
    from management.models.unconfirmed_matches import ProposedMatch
    all_unclosed_unconfirmed = ProposedMatch.objects.filter(closed=False)
    
    # unconfirmed matches reminders
    for unclosed in all_unclosed_unconfirmed:
        if unclosed.is_expired(close_if_expired=True, send_mail_if_expired=True):
            continue
        unclosed.is_reminder_due(send_reminder=True)
        
@shared_task
def check_registration_reminders():
    """
    Reoccuring task to check if we need to send a registration reminder email to the user
    we send these emails earliest 3h after registration!
    
    They include:
    - email unverified reminder
    - user from unfinished reminder 1
    - user from unfinished reminder 2
    """
    from datetime import datetime, time
    from management.models.state import State
    from management.models.user import User
    from django.db.models import Q
    from django.utils import timezone

    _3hrs_ago = timezone.now() - timezone.timedelta(hours=3)

    unverified_email_unfinished_userform = User.objects.filter(
        Q(date_joined__lte=_3hrs_ago),
        settings__email_settings__email_verification_reminder1=False,
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=False)
    
    for user in unverified_email_unfinished_userform:
        ems = user.settings.email_settings
        ems.send_email_verification_reminder1(user)
        
    _two_days_ago = timezone.now() - timezone.timedelta(days=2)
    
    _tree_days_ago = timezone.now() - timezone.timedelta(days=3)
        
    verified_email_unifinished_userform_reminder1 = User.objects.filter(
        Q(date_joined__lte=_two_days_ago),
        settings__email_settings__user_form_unfinished_reminder1=False,
        settings__email_settings__user_form_unfinished_reminder2=False,
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=True)

    for user in verified_email_unifinished_userform_reminder1:
        ems = user.settings.email_settings
        ems.send_user_form_unfinished_reminder1(user)

    verified_email_unifinished_userform_reminder2 = User.objects.filter(
        Q(date_joined__lte=_tree_days_ago),
        settings__email_settings__user_form_unfinished_reminder1=True,
        settings__email_settings__user_form_unfinished_reminder2=False,
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=True)
    
    # TODO: can there be any order issue here? something with users appearing in a second filter list before they should?

    for user in verified_email_unifinished_userform_reminder2:
        ems = user.settings.email_settings
        ems.send_user_form_unfinished_reminder2(user)
    
@shared_task
def check_match_still_in_contact_emails():
    from management.models.matches import Match
    from django.db.models import Q
    from django.utils import timezone
    from emails import mails
    
    matches_older_than_3_weeks = Match.objects.filter(
        Q(created_at__lte=timezone.now() - timezone.timedelta(days=21)),
        still_in_contact_mail_send=False,
    ).exclude(
        support_matching=True
    )
    
    report = []
    
    for match in matches_older_than_3_weeks:
        
        for comb in [(match.user1, match.user2), (match.user2, match.user1)]:
            comb[0].send_email(
                subject="Matching noch aktiv?",
                mail_data=mails.get_mail_data_by_name("still_in_contact"),
                mail_params=mails.StillInContactParams(
                    first_name=comb[0].profile.first_name,
                    partner_first_name=comb[1].profile.first_name,
                ),
                emulated_send=True
            )
        report.append({
            "kind" : "send_still_in_contanct_email",
            "match": str(match.pk),
            "user1": str(match.user1.hash),
            "user2": str(match.user2.hash)
        })
        match.still_in_contact_mail_send = True
        match.save()
    return report
    
    

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

@shared_task
def request_streamed_ai_response(messages, model="gpt-3.5-turbo", backend="default"):
    from openai import OpenAI
    from django.conf import settings
    from django.http import StreamingHttpResponse
    from rest_framework.decorators import api_view, authentication_classes
    from management.models.state import State
    from django.views import View
    from django.urls import path, re_path
    from django.contrib.auth.mixins import LoginRequiredMixin
    from rest_framework.authentication import SessionAuthentication
    from django.http import HttpResponseBadRequest
    import json
    import time
    
    
    def get_base_ai_client():
        if backend == "default":
            return OpenAI(
                api_key=settings.AI_OPENAI_API_KEY,
            )
        else:
            return OpenAI(
                api_key=settings.AI_API_KEY,
                base_url=settings.AI_BASE_URL,
            )


    client = get_base_ai_client()

    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        stream=True  # this time, we set stream=True
    )
    
    
    message_dt = ""
    message_ft = ""
    
    c = 0
    update_mod = 1

    for chunk in completion:
        content = chunk.choices[0].delta.content
        message_dt = content if content else ""
        message_ft += message_dt
        

        c+=1
        if c % update_mod == 0:
            request_streamed_ai_response.backend.mark_as_started(
                request_streamed_ai_response.request.id,
                progress=message_ft
            )
            c = 0
    request_streamed_ai_response.backend.mark_as_started(
        request_streamed_ai_response.request.id,
        progress=message_ft
    )
    


@shared_task
def matching_algo_v2(
    user_pk,
    consider_only_registered_within_last_x_days=None,
    exlude_user_ids=[]
):
    
    from management.api.scores import calculate_scores_user
    
    def report_progress(progress):
        matching_algo_v2.backend.mark_as_started(
            matching_algo_v2.request.id,
            progress=progress
        )
        
    res = calculate_scores_user(
        user_pk,
        consider_only_registered_within_last_x_days=consider_only_registered_within_last_x_days,
        report=report_progress,
        exlude_user_ids=exlude_user_ids
    )
    
    return res

@shared_task
def burst_calculate_matching_scores(
    user_combinations = []
):
    from management.api.scores import score_between_db_update
    from management.models.user import User
    """
    Calculates the matching scores for all users requiring a match at the moment 
    """
    print("combination")
    
    def report_progress(progress):
        burst_calculate_matching_scores.backend.mark_as_started(
            burst_calculate_matching_scores.request.id,
            progress=progress
        )
        
    total_combinations = len(user_combinations)
    combinations_processed = 0
    
    report_progress({
        "total_combinations": total_combinations,
        "combinations_processed": combinations_processed,
    })
        
    for comb in user_combinations:
        user1 = User.objects.get(pk=comb[0])
        user2 = User.objects.get(pk=comb[1])
        score_between_db_update(
            user1,
            user2
        )
        combinations_processed += 1
        
        report_progress({
            "total_combinations": total_combinations,
            "combinations_processed": combinations_processed,
        })
        
    return {
        "total_combinations": total_combinations,
        "combinations_processed": combinations_processed,
    }
        
    
        
    
    
