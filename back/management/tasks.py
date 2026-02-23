import math
import random
from datetime import datetime, timedelta, timezone

from celery import shared_task
from cookie_consent.models import Cookie, CookieGroup
from django.db.models import Q
from django.utils import timezone as dj_timezone
from translations import get_translation

from management.models.backend_state import BackendState
from management.models.banner import Banner
from management.models.community_events import CommunityEvent
from management.models.state import State
from management.models.user import User

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
    Though we do default to german here for now!
    """
    if BackendState.are_default_community_events_set(set_true=True):
        return "Events already created! If they were deleted you should delete the state!"

    CommunityEvent.objects.create(
        title=get_translation("community_event.coffe_break", lang="de"),
        description="Zusammenkommen der Community – lerne das Team hinter Little World und andere Nutzer:innen bei einer gemütlichen Tasse Kaffee oder Tee kennen.",
        time=datetime(2022, 11, 29, 12, 00, 00, 00, timezone.utc),
        active=True,
        frequency=CommunityEvent.EventFrequencyChoices.WEEKLY,
    )

    return "events created!"


@shared_task
def create_default_banners():
    """
    Creates base banners,
    we store this here since we are using translations here!
    Though we do default to german here for now!
    """
    if BackendState.are_default_banners_set(set_true=True):
        return "Banners already set according to  backend state! If they were deleted you should delete the state!"

    Banner.objects.create(
        name="Learner Banner",
        title="Lovely Learner",
        text="Lovely learner, Little World is free and will always be free. But in order to keep us going we need your support. Please head to our support page to find out the ways you can help us.",
        active=False,
        cta_1_url="/app/our-world/",
        cta_1_text="Support us",
        image="",
        image_alt="background image",
    )

    Banner.objects.create(
        name="Volunteer Banner",
        title="Lovely Volunteer",
        text="Lovely volunteer, Little World is free and will always be free. But in order to keep us going we need your support. Please head to our support page to find out the ways you can help us.",
        active=False,
        cta_1_url="/app/our-world/",
        cta_1_text="Support us",
        image="",
        image_alt="background image",
    )

    return "banners created!"


@shared_task
def create_default_cookie_groups():
    if BackendState.are_default_cookies_set(set_true=True):
        return "events already set, sais backend state! If they were deleted you should delete the state!"

    analytics_cookiegroup = CookieGroup.objects.create(
        varname="analytics",
        name="analytics_cookiegroup",
        description="Google analytics and Facebook Pixel",
        is_required=False,
        is_deletable=True,
    )

    CookieGroup.objects.create(
        varname="lw_func_cookies",
        name="FunctionalityCookies",
        description="Cookies required for basic functionality of Little World",
        is_required=True,
        is_deletable=False,
    )

    Cookie.objects.create(
        cookiegroup=analytics_cookiegroup,
        name="google_analytics_cookie",
        description="Google anlytics cookies and scripts",
        include_srcs=["https://www.googletagmanager.com/gtag/js?id=AW-10994486925"],
        include_scripts=[
            "\nwindow.dataLayer = window.dataLayer || [];\n"
            + "function gtag(){dataLayer.push(arguments);}\n"
            + "gtag('js', new Date());\n"
            + "gtag('config', 'AW-10994486925');\n"
            + "gtag('config', 'AW-10992228532');"
        ],
    )

    facebook_init_script = (
        "\n!function(f,b,e,v,n,t,s)\n{if(f.fbq)return;n=f.fbq=function(){n.callMethod?\n"
        + "n.callMethod.apply(n,arguments):n.queue.push(arguments)};\nif(!f._fbq)f._fbq=n;n.push=n;"
        + "n.loaded=!0;n.version='2.0';\nn.queue=[];t=b.createElement(e);t.async=!0;\nt.src=v;s=b.getElementsByTagName(e)[0];"
        + "\ns.parentNode.insertBefore(t,s)}(window, document,'script',\n'https://connect.facebook.net/en_US/fbevents.js');\n"
        + "fbq('init', '1108875150004843');\nfbq('track', 'PageView');\n    "
    )

    Cookie.objects.create(
        cookiegroup=analytics_cookiegroup,
        name="facebook_pixel_cookie",
        description="Facebook Pixel analytics cookies and scripts",
        include_srcs=[],
        include_scripts=[facebook_init_script],
    )


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
    usr.profile.country_of_residence = "DE"
    usr.profile.postal_code = 20480
    usr.profile.description = base_management_user_description
    usr.profile.add_profile_picture_from_local_path("/back/dev_test_data/oliver_berlin_management_user_profile_pic.jpg")
    usr.profile.save()
    return "sucessfully filled base management user profile"


@shared_task
def fill_base_management_user_tim_profile():
    if BackendState.is_base_management_user_profile_filled(set_true=True):
        return  # Allready filled base management user profile

    from management.controller import get_base_management_user
    from management.models.state import State

    base_management_user_description = """
Hello there 👋🏼

Im the co-founder and CTO of little world. And as of today I'm your support match!
We are currently working hard to improve our matching process and give to offer you the best experience possible.

Feel free to send me any question or suggestions.
I'll take the time to answer all your messages but I might take a little time to do so.
"""
    usr = get_base_management_user()
    usr.profile.birth_year = 1999
    usr.profile.country_of_residence = "DE"
    usr.profile.postal_code = 52064
    usr.profile.description = base_management_user_description
    usr.profile.add_profile_picture_from_local_path("/back/dev_test_data/tim_schupp_base_management_profile_new.jpeg")

    usr.state.extra_user_permissions.append(State.ExtraUserPermissionChoices.MATCHING_USER)
    usr.state.save()
    usr.profile.save()


@shared_task
def check_prematch_email_reminders_and_expirations():
    """
    Reoccuring task to check for email reminders that should be send out
    also check if there are expired unconfirmed_matches
    """
    from management.models.state import State
    from management.models.unconfirmed_matches import ProposedMatch

    all_unclosed_unconfirmed = ProposedMatch.objects.filter(closed=False)

    # unconfirmed matches reminders
    for unclosed in all_unclosed_unconfirmed:
        if unclosed.is_expired(close_if_expired=True, send_mail_if_expired=True):
            # Now we have to set the learner to unresponsive = True and to searching = IDLE unless user has match priority
            learner_state = unclosed.learner_when_created.state
            if not learner_state.has_match_priority:
                learner_state.searching_state = State.SearchingStateChoices.IDLE
                learner_state.unresponsive = True
                learner_state.append_notes(f"Set to unresponsive cause let proposal expire: 'proposal:{unclosed.pk}'")
                learner_state.save()
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
    from django.db.models import Q
    from django.utils import timezone

    _3hrs_ago = timezone.now() - timezone.timedelta(hours=3)

    unverified_email_unfinished_userform = User.objects.filter(
        Q(date_joined__lte=_3hrs_ago),
        settings__email_settings__email_verification_reminder1=False,
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=False,
    )

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
        state__email_authenticated=True,
    )

    for user in verified_email_unifinished_userform_reminder1:
        ems = user.settings.email_settings
        ems.send_user_form_unfinished_reminder1(user)

    verified_email_unifinished_userform_reminder2 = User.objects.filter(
        Q(date_joined__lte=_tree_days_ago),
        settings__email_settings__user_form_unfinished_reminder1=True,
        settings__email_settings__user_form_unfinished_reminder2=False,
        state__user_form_state=State.UserFormStateChoices.UNFILLED,
        state__email_authenticated=True,
    )

    for user in verified_email_unifinished_userform_reminder2:
        ems = user.settings.email_settings
        ems.send_user_form_unfinished_reminder2(user)


@shared_task
def request_streamed_ai_response(messages, model="gpt-3.5-turbo", backend="default"):
    from django.conf import settings
    from openai import OpenAI

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
        stream=True,  # this time, we set stream=True
    )

    message_dt = ""
    message_ft = ""

    c = 0
    update_mod = 1

    for chunk in completion:
        content = chunk.choices[0].delta.content
        message_dt = content if content else ""
        message_ft += message_dt

        c += 1
        if c % update_mod == 0:
            request_streamed_ai_response.backend.mark_as_started(
                request_streamed_ai_response.request.id, progress=message_ft
            )
            c = 0
    request_streamed_ai_response.backend.mark_as_started(request_streamed_ai_response.request.id, progress=message_ft)


@shared_task
def matching_algo_v2(user_pk, consider_only_registered_within_last_x_days=None, exlude_user_ids=[]):
    from management.api.scores import calculate_scores_user

    def report_progress(progress):
        matching_algo_v2.backend.mark_as_started(matching_algo_v2.request.id, progress=progress)

    res = calculate_scores_user(
        user_pk,
        consider_only_registered_within_last_x_days=consider_only_registered_within_last_x_days,
        report=report_progress,
        exlude_user_ids=exlude_user_ids,
    )

    return res


@shared_task
def burst_calculate_matching_scores(user_combinations=[]):
    from management.api.scores import score_between_db_update

    """
    Calculates the matching scores for all users requiring a match at the moment 
    """
    print("combination")

    def report_progress(progress):
        burst_calculate_matching_scores.backend.mark_as_started(
            burst_calculate_matching_scores.request.id, progress=progress
        )

    total_combinations = len(user_combinations)
    combinations_processed = 0

    report_progress(
        {
            "total_combinations": total_combinations,
            "combinations_processed": combinations_processed,
        }
    )

    for comb in user_combinations:
        user1 = User.objects.get(pk=comb[0])
        user2 = User.objects.get(pk=comb[1])
        score_between_db_update(user1, user2)
        combinations_processed += 1

        report_progress(
            {
                "total_combinations": total_combinations,
                "combinations_processed": combinations_processed,
            }
        )

    random_delay = math.floor(random.random() * 5)

    mark_burst_task_completed_check_for_finish.apply_async(
        (burst_calculate_matching_scores.request.id,), countdown=2 + random_delay
    )

    return {
        "total_combinations": total_combinations,
        "combinations_processed": combinations_processed,
    }


@shared_task
def mark_burst_task_completed_check_for_finish(task_id=None):
    from management.models.backend_state import BackendState

    current_caluclation = BackendState.objects.filter(slug=BackendState.BackendStateEnum.updating_matching_scores)

    if not current_caluclation.exists():
        return {"status": "done"}
    current_caluclation = current_caluclation.first()

    current_calculation_task_ids = current_caluclation.meta.get("tasks", [])
    completed_task_ids = current_caluclation.meta.get("completed_tasks", [])

    if task_id not in current_calculation_task_ids:
        return {"status": "done"}

    current_calculation_task_ids.remove(task_id)
    completed_task_ids.append(task_id)

    if len(current_calculation_task_ids) == 0:
        current_caluclation.delete()
    else:
        current_caluclation.meta["tasks"] = current_calculation_task_ids
        current_caluclation.meta["completed_tasks"] = completed_task_ids
        current_caluclation.save()

    return {"status": "done"}


@shared_task
def record_bucket_ids():
    from management.api.match_journey_filter_list import MATCH_JOURNEY_FILTERS
    from management.api.user_advanced_filter_lists import FILTER_LISTS
    from management.models.stats import Statistic

    # 1 - record all user bucket ids
    data = {}
    for fl in FILTER_LISTS:
        try:
            qs = fl.queryset()
            data[fl.name] = list(qs.values_list("id", flat=True))
        except Exception:
            # the id -500 indicates a filter error!
            data[fl.name] = str(-500)

    Statistic.objects.create(kind=Statistic.StatisticTypes.USER_BUCKET_IDS, data=data)

    # 2 - record all match bucket ids
    data = {}
    for fl in MATCH_JOURNEY_FILTERS:
        try:
            qs = fl.queryset()
            data[fl.name] = list(qs.values_list("id", flat=True))
        except Exception:
            data[fl.name] = str(-500)

    Statistic.objects.create(kind=Statistic.StatisticTypes.MATCH_BUCKET_IDS, data=data)


@shared_task
def send_dynamic_email_backgruound(
    template_name,
    user_id=None,
):
    from django.core.mail import EmailMessage
    from django.template import Context, Template
    from emails.api.emails_config import EMAILS_CONFIG
    from emails.api.render_template import prepare_dynamic_template_context
    from emails.models import EmailLog

    from management.controller import get_base_management_user

    user = User.objects.get(id=user_id)

    dynamic_template_info, _context = prepare_dynamic_template_context(template_name=template_name, user_id=user.id)
    html_template = Template(dynamic_template_info["template"])
    html = html_template.render(Context(_context))
    subject = Template(dynamic_template_info["subject"])
    subject = subject.render(Context(_context))

    mail_log = EmailLog.objects.create(
        log_version=1,
        sender=get_base_management_user(),
        receiver=user,
        template=template_name,
        is_dyanmic_email=True,
        data={"html": html, "params": _context, "user_id": user.id, "match_id": None, "subject": subject},
    )

    try:
        from_email = EMAILS_CONFIG.senders["noreply"]
        mail = EmailMessage(
            subject=subject,
            body=html,
            from_email=from_email,
            to=[user],
        )
        mail.content_subtype = "html"
        mail.send(fail_silently=False)
        mail_log.sucess = True
        mail_log.save()
    except Exception:
        mail_log.sucess = False
        mail_log.save()


@shared_task
def send_email_background(
    template_name,
    user_id=None,
    match_id=None,
    proposed_match_id=None,
    context={},
    patenmatch=False,
    patenmatch_org=False,
    emulated_send=False,
):
    from emails.api.send_email import send_template_email

    if not patenmatch:
        send_template_email(
            template_name,
            user_id=user_id,
            match_id=match_id,
            proposed_match_id=proposed_match_id,
            emulated_send=emulated_send,
            context=context,
        )
    else:
        from patenmatch.models import PatenmatchOrganization, PatenmatchUser

        def retrieve_user_model():
            return PatenmatchOrganization if patenmatch_org else PatenmatchUser

        send_template_email(
            template_name,
            user_id=user_id,
            match_id=match_id,
            proposed_match_id=proposed_match_id,
            emulated_send=emulated_send,
            context=context,
            retrieve_user_model=retrieve_user_model,
        )


@shared_task
def slack_notify_communication_channel_async(message):
    from management.api.slack import notify_communication_channel

    notify_communication_channel(message)


@shared_task
def slack_notify_security_channel_async(message):
    from management.api.slack import notify_security_channel

    notify_security_channel(message)


@shared_task
def hourly_check_banner_activation():
    from django.utils import timezone

    current_time = timezone.now()

    bc = {
        "activated": [],
        "deactivated": [],
    }

    # 1 - check for banners that might need activation
    p_activation_banners = Banner.objects.filter(activation_time__isnull=False, active=False)

    # activate banners that need activation
    for banner in p_activation_banners:
        if banner.activation_time <= current_time:
            banner.active = True
            banner.save()
            bc["activated"].append(banner.id)

    # 2 - deactivate banners that need deactivation
    p_deactivation_banners = Banner.objects.filter(expiration_time__isnull=False, active=True)

    for banner in p_deactivation_banners:
        if banner.expiration_time <= current_time:
            banner.active = False
            banner.save()
            bc["deactivated"].append(banner.id)
    return bc


@shared_task(
    autoretry_for=(),
    retry_kwargs={"max_retries": 0},
    reject_on_worker_lost=True,
    acks_late=False,
    bind=True,
    expires=300,
    time_limit=300,
)
def send_sms_background(self, user_hash, message):
    """
    Send SMS background task that never retries on failure.
    If the task fails, it should fail permanently to prevent duplicate SMS sending.
    """
    from django.utils import timezone

    from management.controller import get_base_management_user
    from management.models.sms import SmsModel
    from management.models.user import User

    recent_sms = SmsModel.objects.filter(
        recipient__hash=user_hash, message=message, created_at__gte=timezone.now() - timezone.timedelta(hours=2)
    ).exists()

    if recent_sms:
        print(f"Skipping duplicate SMS for user {user_hash} - already sent within last 2 hours")
        return {"status": "skipped", "reason": "duplicate_message"}

    try:
        receipient = User.objects.get(hash=user_hash)
        result = receipient.sms(send_initator=get_base_management_user(), message=message)
        return {"status": "sent", "result": result}
    except Exception as e:
        print(f"SMS task failed for user {user_hash}: {str(e)}")
        raise  # Re-raise to mark task as failed


@shared_task
def automatic_emails_u023_u024_u025():
    """
    Sends automatic emails to users who have not booked an onboarding call after completing the user form
    """
    from django.conf import settings

    from management.models.pre_matching_appointment import PreMatchingAppointment
    from management.models.user import User

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__U023_U024_U025)

    reminder = {
        "automatic-emails-u023": [3, False, False, False],
        "automatic-emails-u024": [7, True, False, False],
        "automatic-emails-u025": [14, True, True, False],
    }
    users_sended = []
    for template, (days, three_days_reminder, seven_days_reminder, fourteen_days_reminder) in reminder.items():
        users = User.objects.filter(
            state__user_form_completed_at__lte=dj_timezone.now() - timedelta(days=days),
            state__had_prematching_call=False,
            state__user_form_completed_3_days_reminder_send=three_days_reminder,
            state__user_form_completed_7_days_reminder_send=seven_days_reminder,
            state__user_form_completed_14_days_reminder_send=fourteen_days_reminder,
        )
        user_prematching_join = PreMatchingAppointment.objects.filter(user__in=users)
        users = users.exclude(id__in=user_prematching_join.values_list("user", flat=True))

        users_sended.append(users)
        for user in users:
            send_email_background.delay(template, user_id=user.id, emulated_send=emulated_send)
            user.state.set_user_form_completed_reminder_sent(days)

    return {
        "status": "sent",
        "users_u023": users_sended[0],
        "users_u024": users_sended[1],
        "users_u025": users_sended[2],
    }


@shared_task
def automatic_emails_m012_m013_m014():
    """
    Confirmed match between users but no interaction yet (no messages or video calls)
    """
    from django.conf import settings

    from management.models.matches import Match

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__M012_M013_M014)

    reminder = {
        "automatic-emails-m012": [2, False, False, False],
        "automatic-emails-m013": [7, True, False, False],
        "automatic-emails-m014": [14, True, True, False],
    }

    matches_found = []

    for template, (days, two_days_reminder, seven_days_reminder, fourteen_days_reminder) in reminder.items():
        matches = Match.objects.filter(
            confirmed=True,
            total_messages_counter=0,
            total_mutal_video_calls_counter=0,
            latest_interaction_at__lte=dj_timezone.now() - timedelta(days=days),
            interaction_reminder_2_days_send=two_days_reminder,
            interaction_reminder_7_days_send=seven_days_reminder,
            interaction_reminder_14_days_send=fourteen_days_reminder,
            support_matching=False,
        )

        for match in matches:
            send_email_background.delay(
                template,
                user_id=match.user1.id,
                match_id=match.id,
                emulated_send=emulated_send,
                context={"link_url": "https://drive.google.com/file/d/1XcY6_OMZES5QJoMkc6jbEzwYNdCWrnaU/view"},
            )
            send_email_background.delay(
                template,
                user_id=match.user2.id,
                match_id=match.id,
                emulated_send=emulated_send,
                context={"link_url": "https://drive.google.com/file/d/1XcY6_OMZES5QJoMkc6jbEzwYNdCWrnaU/view"},
            )

            match days:
                case 2:
                    match.interaction_reminder_2_days_send = True
                case 7:
                    match.interaction_reminder_7_days_send = True
                case 14:
                    match.interaction_reminder_14_days_send = True

            match.save()
        matches_found.append(matches)

    return {
        "status": "sent",
        "matches_m012": matches_found[0],
        "matches_m013": matches_found[1],
        "matches_m014": matches_found[2],
    }


@shared_task
def automatic_emails_m023():
    """
    Notify user when the didnt respond to a chat message for 3 days
    """
    from chat.models import Chat
    from django.conf import settings
    from django.db.models import Max

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__M023)

    chats = (
        Chat.objects.annotate(last_message_at=Max("message__created"))
        .filter(last_message_at__lte=dj_timezone.now() - timedelta(days=3), three_days_inactive_email_send=False)
        .exclude(
            Q(u1__is_staff=True)
            | Q(u2__is_staff=True)
            | Q(u1__state__extra_user_permissions__contains="matching-user")
            | Q(u2__state__extra_user_permissions__contains="matching-user")
        )
    )
    inactive_chats = []
    for chat in chats:
        # the chat is for three days inactive, set the respective flag
        chat.three_days_inactive_email_send = True
        chat.save()
        inactive_chats.append(chat)

        # send email to the user that received the last message
        last_message = chat.get_newest_message()
        send_email_background.delay(
            "automatic-emails-m023", user_id=last_message.recipient.id, emulated_send=emulated_send
        )

    return {"status": "sent", "inactive_chats": inactive_chats}


@shared_task
def automatic_emails_m024_m025():
    """
    Notify user when the didnt respond to a chat message for 7 days
    """
    from chat.models import Chat
    from django.conf import settings
    from django.db.models import Max

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__M024_M025)

    # get all chats, excluding admin and matching users
    chats = (
        Chat.objects.annotate(last_message_at=Max("message__created"))
        .filter(last_message_at__lte=dj_timezone.now() - timedelta(days=7), seven_days_inactive_email_send=False)
        .exclude(
            Q(u1__is_staff=True)
            | Q(u2__is_staff=True)
            | Q(u1__state__extra_user_permissions__contains="matching-user")
            | Q(u2__state__extra_user_permissions__contains="matching-user")
        )
    )

    inactive_chats = []

    for chat in chats:
        # the chat is for seven days inactive, set the respective flag
        chat.seven_days_inactive_email_send = True
        chat.save()
        inactive_chats.append(chat)

        last_message = chat.get_newest_message()

        # send email to the user that received the last message
        send_email_background.delay(
            "automatic-emails-m024", user_id=last_message.recipient.id, emulated_send=emulated_send
        )

        # send email to the person that was ghosted
        send_email_background.delay(
            "automatic-emails-m025", user_id=last_message.sender.id, emulated_send=emulated_send
        )

    return {"status": "sent", "inactive_chats": [str(chat.uuid) for chat in inactive_chats]}


@shared_task
def automatic_emails_m031_m032_m033_m042():
    """
    No video call for 7, 14 and 21 days after first chat message or no video call for 30 days after the first interaction
    """
    from django.conf import settings

    from management.models.matches import Match

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__M031_M032_M033_M042)

    # 1 - automatic-emails-m031
    matches_m031 = Match.objects.filter(
        first_interaction_at__isnull=False,
        first_interaction_at__lte=dj_timezone.now() - timedelta(days=7),
        first_interaction_at__gt=dj_timezone.now() - timedelta(days=14),
        total_mutal_video_calls_counter=0,
        auto_email_m031_send=False,
        support_matching=False,
    )
    matches_m031_uuids = [str(uuid) for uuid in matches_m031.values_list("uuid", flat=True)]
    for match in matches_m031:
        send_email_background.delay(
            "automatic-emails-m031", user_id=match.user1.id, match_id=match.id, emulated_send=emulated_send
        )
        send_email_background.delay(
            "automatic-emails-m031", user_id=match.user2.id, match_id=match.id, emulated_send=emulated_send
        )

        match.auto_email_m031_send = True
        match.save()

    redirect_slugs = {
        "redirect_slug_no": "info-screen",
        "redirect_slug_yes": "match-form1",
    }

    # 2 - automatic-emails-m032
    matches_m032 = Match.objects.filter(
        first_interaction_at__isnull=False,
        first_interaction_at__lte=dj_timezone.now() - timedelta(days=14),
        first_interaction_at__gt=dj_timezone.now() - timedelta(days=21),
        total_mutal_video_calls_counter=0,
        auto_email_m032_send=False,
        support_matching=False,
    )
    matches_m032_uuids = [str(uuid) for uuid in matches_m032.values_list("uuid", flat=True)]
    for match in matches_m032:
        send_email_background.delay(
            "automatic-emails-m032",
            user_id=match.user1.id,
            match_id=match.id,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )
        send_email_background.delay(
            "automatic-emails-m032",
            user_id=match.user2.id,
            match_id=match.id,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )

        match.auto_email_m032_send = True
        match.save()

    # 3 - automatic-emails-m033
    matches_m033 = Match.objects.filter(
        first_interaction_at__isnull=False,
        first_interaction_at__lte=dj_timezone.now() - timedelta(days=21),
        first_interaction_at__gt=dj_timezone.now() - timedelta(days=30),
        total_mutal_video_calls_counter=0,
        auto_email_m033_send=False,
        support_matching=False,
    )
    matches_m033_uuids = [str(uuid) for uuid in matches_m033.values_list("uuid", flat=True)]
    for match in matches_m033:
        send_email_background.delay(
            "automatic-emails-m033",
            user_id=match.user1.id,
            match_id=match.id,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )
        send_email_background.delay(
            "automatic-emails-m033",
            user_id=match.user2.id,
            match_id=match.id,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )

        match.auto_email_m033_send = True
        match.save()

    # 4 - automatic-emails-m042
    matches_m042 = Match.objects.filter(
        first_interaction_at__isnull=False,
        first_interaction_at__lte=dj_timezone.now() - timedelta(days=30),
        total_mutal_video_calls_counter=0,
        auto_email_m042_send=False,
        support_matching=False,
    )
    matches_m042_uuids = [str(uuid) for uuid in matches_m042.values_list("uuid", flat=True)]
    for match in matches_m042:
        send_email_background.delay(
            "automatic-emails-m042",
            user_id=match.user1.id,
            match_id=match.id,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )
        send_email_background.delay(
            "automatic-emails-m042",
            user_id=match.user2.id,
            match_id=match.id,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )

        match.auto_email_m042_send = True
        match.save()

    return {
        "status": "sent",
        "matches_m031": matches_m031_uuids,
        "matches_m032": matches_m032_uuids,
        "matches_m033": matches_m033_uuids,
        "matches_m042": matches_m042_uuids,
    }


@shared_task
def automatic_emails_u072_u073_u074():
    """
    User searching for the first time still no matching
    """
    from django.conf import settings

    from management.models.user import User

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__U072_U073_U074)

    users_u072 = User.objects.filter(
        state__onboarding_call_completed_at__lte=dj_timezone.now() - timedelta(days=10),
        state__onboarding_call_completed_at__gt=dj_timezone.now() - timedelta(days=21),
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
        state__auto_email_u072_send=False,
        state__has_received_first_match=False,
    )
    users_u072_hashes = list(users_u072.values_list("hash", flat=True))
    for user in users_u072:
        send_email_background.delay("automatic-emails-u072", user_id=user.id, emulated_send=emulated_send)
        user.state.auto_email_u072_send = True
        user.state.save()

    users_u073 = User.objects.filter(
        state__onboarding_call_completed_at__lte=dj_timezone.now() - timedelta(days=21),
        state__onboarding_call_completed_at__gt=dj_timezone.now() - timedelta(days=30),
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
        state__auto_email_u073_send=False,
        state__has_received_first_match=False,
    )
    users_u073_hashes = list(users_u073.values_list("hash", flat=True))
    for user in users_u073:
        send_email_background.delay("automatic-emails-u073", user_id=user.id, emulated_send=emulated_send)
        user.state.auto_email_u073_send = True
        user.state.save()

    users_u074 = User.objects.filter(
        state__onboarding_call_completed_at__lte=dj_timezone.now() - timedelta(days=30),
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
        state__auto_email_u074_send=False,
        state__has_received_first_match=False,
    )
    users_u074_hashes = list(users_u074.values_list("hash", flat=True))
    for user in users_u074:
        send_email_background.delay("automatic-emails-u074", user_id=user.id, emulated_send=emulated_send)
        user.state.auto_email_u074_send = True
        user.state.save()

    return {
        "status": "sent",
        "users_u072": users_u072_hashes,
        "users_u073": users_u073_hashes,
        "users_u074": users_u074_hashes,
    }


@shared_task
def automatic_emails_u082_u083_u084():
    """
    User searching for the first time still no matching
    """
    from django.conf import settings

    from management.models.user import User

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__U081_U082_U083_U084)

    # These emails are only triggered if u081 is triggered, this is triggered automatically when the user searches AGAIN
    users_u082 = User.objects.filter(
        state__onboarding_call_completed_at__lte=dj_timezone.now() - timedelta(days=10),
        state__onboarding_call_completed_at__gt=dj_timezone.now() - timedelta(days=21),
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__had_prematching_call=True,
        state__auto_emails_u081_send=True,
        state__auto_emails_u082_send=False,
        state__has_received_first_match=True,
    )
    users_u082_hashes = list(users_u082.values_list("hash", flat=True))
    for user in users_u082:
        send_email_background.delay("automatic-emails-u082", user_id=user.id, emulated_send=emulated_send)
        user.state.auto_emails_u082_send = True
        user.state.save()

    users_u083 = User.objects.filter(
        state__onboarding_call_completed_at__lte=dj_timezone.now() - timedelta(days=21),
        state__onboarding_call_completed_at__gt=dj_timezone.now() - timedelta(days=30),
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__auto_emails_u081_send=True,
        state__auto_emails_u083_send=False,
        state__has_received_first_match=True,
    )
    users_u083_hashes = list(users_u083.values_list("hash", flat=True))
    for user in users_u083:
        send_email_background.delay("automatic-emails-u083", user_id=user.id, emulated_send=emulated_send)
        user.state.auto_emails_u083_send = True
        user.state.save()

    users_u084 = User.objects.filter(
        state__onboarding_call_completed_at__lte=dj_timezone.now() - timedelta(days=30),
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__auto_emails_u081_send=True,
        state__auto_emails_u084_send=False,
        state__has_received_first_match=True,
    )
    users_u084_hashes = list(users_u084.values_list("hash", flat=True))
    for user in users_u084:
        send_email_background.delay("automatic-emails-u084", user_id=user.id, emulated_send=emulated_send)
        user.state.auto_emails_u084_send = True
        user.state.save()

    return {
        "status": "sent",
        "users_u082": users_u082_hashes,
        "users_u083": users_u083_hashes,
        "users_u084": users_u084_hashes,
    }


@shared_task
def daily_auto_email_report():
    from collections import defaultdict
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone
    from emails.models import EmailLog

    from management.api.slack import notify_security_channel

    enabled_emails = {
        "AUTOMATIC_EMAILS__U023_U024_U025": {
            "enabled": settings.ENABLE_AUTO_EMAILS__U023_U024_U025,
            "emulated": settings.EMULATE_AUTO_EMAILS__U023_U024_U025,
        },
        "AUTOMATIC_EMAILS__M012_M013_M014": {
            "enabled": settings.ENABLE_AUTO_EMAILS__M012_M013_M014,
            "emulated": settings.EMULATE_AUTO_EMAILS__M012_M013_M014,
        },
        "AUTOMATIC_EMAILS__M023": {
            "enabled": settings.ENABLE_AUTO_EMAILS__M023,
            "emulated": settings.EMULATE_AUTO_EMAILS__M023,
        },
        "AUTOMATIC_EMAILS__M024_M025": {
            "enabled": settings.ENABLE_AUTO_EMAILS__M024_M025,
            "emulated": settings.EMULATE_AUTO_EMAILS__M024_M025,
        },
        "AUTOMATIC_EMAILS__M031_M032_M033_M042": {
            "enabled": settings.ENABLE_AUTO_EMAILS__M031_M032_M033_M042,
            "emulated": settings.EMULATE_AUTO_EMAILS__M031_M032_M033_M042,
        },
        "AUTOMATIC_EMAILS__U072_U073_U074": {
            "enabled": settings.ENABLE_AUTO_EMAILS__U072_U073_U074,
            "emulated": settings.EMULATE_AUTO_EMAILS__U072_U073_U074,
        },
        "AUTOMATIC_EMAILS__U081_U082_U083_U084": {
            "enabled": settings.ENABLE_AUTO_EMAILS__U081_U082_U083_U084,
            "emulated": settings.EMULATE_AUTO_EMAILS__U081_U082_U083_U084,
        },
    }

    check_emails = [
        "automatic-emails-u023",
        "automatic-emails-u024",
        "automatic-emails-u025",
        "automatic-emails-m012",
        "automatic-emails-m013",
        "automatic-emails-m014",
        "automatic-emails-m023",
        "automatic-emails-m024",
        "automatic-emails-m025",
        "automatic-emails-m031",
        "automatic-emails-m032",
        "automatic-emails-m033",
        "automatic-emails-m042",
        "automatic-emails-u072",
        "automatic-emails-u073",
        "automatic-emails-u074",
        "automatic-emails-u081",
        "automatic-emails-u082",
        "automatic-emails-u083",
        "automatic-emails-u084",
    ]

    # Get yesterday's date range
    now = timezone.now()
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = yesterday_start + timedelta(days=1)

    # Query EmailLog for auto emails sent yesterday
    email_logs = EmailLog.objects.filter(
        template__in=check_emails,
        time__gte=yesterday_start,
        time__lt=yesterday_end,
        sucess=True,
    ).select_related("receiver")

    if not email_logs.exists():
        # No auto emails sent yesterday, send a simple notification
        message = (
            f"*Auto Email Report:* ({yesterday_start.strftime('%Y-%m-%d')})\n\nNo automatic emails were sent yesterday."
        )
        notify_security_channel(message)
        return {"status": "no_emails", "date": yesterday_start.strftime("%Y-%m-%d")}

    # Group emails by template for summary
    email_counts = defaultdict(int)
    # Group emails by user for per-user breakdown
    user_emails = defaultdict(list)

    for log in email_logs:
        email_counts[log.template] += 1
        if log.receiver:
            user_emails[log.receiver].append(log.template)

    # Build the Slack message
    message_parts = [
        f"*Email Report:* ({yesterday_start.strftime('%Y-%m-%d')})",
        "",
        "*Email Summary:*",
    ]

    # Add email counts summary
    for template in check_emails:
        count = email_counts.get(template, 0)
        if count > 0:
            message_parts.append(f"• `{template}`: {count} sent")

    total_emails = sum(email_counts.values())
    message_parts.append(f"\n*Total:* {total_emails} emails sent to {len(user_emails)} users")

    # Add enabled/disabled and emulated status
    message_parts.append("")
    message_parts.append("*Auto Email Settings:*")
    for setting_name, flags in enabled_emails.items():
        enabled_status = "`True`" if flags["enabled"] else "`False`"
        emulated_status = "`True`" if flags["emulated"] else "`False`"
        message_parts.append(f"• {setting_name}: enabled={enabled_status}, emulated={emulated_status}")

    # Add per-user breakdown with links
    message_parts.append("")
    message_parts.append("*Emails Per-User:*")

    for user, templates in sorted(user_emails.items(), key=lambda x: x[0].email if x[0] else ""):
        if user:
            user_url = f"{settings.BASE_URL}/matching/user/{user.id}?tab=emails"
            templates_str = ", ".join(sorted(set(templates)))
            message_parts.append(f"• {user.email}: `{templates_str}` - `{user_url}`")

    message = "\n".join(message_parts)
    notify_security_channel(message)

    return {
        "status": "sent",
        "date": yesterday_start.strftime("%Y-%m-%d"),
        "total_emails": total_emails,
        "unique_users": len(user_emails),
        "email_counts": dict(email_counts),
    }
