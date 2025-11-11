import math
import random
from datetime import datetime, timezone

from celery import shared_task
from cookie_consent.models import Cookie, CookieGroup
from translations import get_translation

from management.models.backend_state import BackendState
from management.models.banner import Banner
from management.models.community_events import CommunityEvent
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

    little_world_functionality_cookies = CookieGroup.objects.create(
        varname="lw_func_cookies",
        name="FunctionalityCookies",
        description="Cookies required for basic functionality of Little World",
        is_required=True,
        is_deletable=False,
    )

    google_analytics_cookie = Cookie.objects.create(
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

    facebook_pixel_cookie = Cookie.objects.create(
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
    from management.models.state import State
    from management.models.unconfirmed_matches import ProposedMatch

    all_unclosed_unconfirmed = ProposedMatch.objects.filter(closed=False)

    # unconfirmed matches reminders
    for unclosed in all_unclosed_unconfirmed:
        if unclosed.is_expired(close_if_expired=True, send_mail_if_expired=True):
            # Now we have to set the learner to unresponsive = True and to searching = IDLE
            learner_state = unclosed.learner_when_created.state
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

    from management.models.state import State

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

    if not (task_id in current_calculation_task_ids):
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
    except Exception as e:
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
):
    from emails.api.send_email import send_template_email

    if not patenmatch:
        send_template_email(
            template_name,
            user_id=user_id,
            match_id=match_id,
            proposed_match_id=proposed_match_id,
            emulated_send=False,
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
            emulated_send=False,
            context=context,
            retrieve_user_model=retrieve_user_model,
        )


@shared_task
def slack_notify_communication_channel_async(message):
    from management.api.slack import notify_communication_channel

    notify_communication_channel(message)


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
    retry_kwargs={'max_retries': 0},
    reject_on_worker_lost=True,
    acks_late=False,
    bind=True
)
def send_sms_background(self, user_hash, message):
    """
    Send SMS background task that never retries on failure.
    If the task fails, it should fail permanently to prevent duplicate SMS sending.
    """
    from django.utils import timezone
    from management.controller import get_base_management_user
    from management.models.user import User
    from management.models.sms import SmsModel

    recent_sms = SmsModel.objects.filter(
        recipient__hash=user_hash,
        message=message,
        created_at__gte=timezone.now() - timezone.timedelta(hours=2)
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