import math
import random
from datetime import datetime, timedelta, timezone

from celery import shared_task
from cookie_consent.models import Cookie, CookieGroup
from django.conf import settings
from django.db.models import Q
from django.utils import timezone as dj_timezone
from translations import get_translation

from management.models.backend_state import BackendState
from management.models.banner import Banner
from management.models.community_events import CommunityEvent
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.state import State
from management.models.user import PushNotificationType, User
from management.permissions import ManagementPermission

from .meta_capi import MetaCAPIClient

"""
also contains general startup celery tasks, most of them are automaticly run when the controller.get_base_management user is created
some of them are managed via models.backend_state.BackendState to ensure they don't run twice!
If you wan't to rerun one of these events make sure to delete the old data *and* the backend state slug!
"""


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": settings.META_CAPI_MAX_RETRIES},
)
def send_meta_capi_events(self, events, event_id=None):
    response = MetaCAPIClient().send_events(events)
    if event_id:
        from tracking.models import ConversionEventLog

        ConversionEventLog.objects.filter(event_id=event_id).update(response=response)
    return response


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
    usr.profile.postal_code = "20480"
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
    usr.profile.postal_code = "52064"
    usr.profile.description = base_management_user_description
    usr.profile.add_profile_picture_from_local_path("/back/dev_test_data/tim_schupp_base_management_profile_new.jpeg")

    usr.grant_permission(ManagementPermission.MATCHING_USER)
    usr.state.save()
    usr.profile.save()


@shared_task
def check_prematch_email_reminders_and_expirations():
    """
    Reoccuring task to check for email reminders that should be send out
    also check if there are expired unconfirmed_matches
    """
    from management.models.unconfirmed_matches import MatchType, ProposedMatch

    all_unclosed_unconfirmed = ProposedMatch.objects.filter(closed=False, match_type=MatchType.STANDARD)

    # unconfirmed matches reminders
    for unclosed in all_unclosed_unconfirmed:
        if unclosed.is_expired(close_if_expired=True, send_mail_if_expired=True):
            # Now we have to set the learner to unresponsive = True and to searching = IDLE unless user has match priority
            confirming_user = unclosed.confirming_user
            if confirming_user is None:
                continue

            learner_state = confirming_user.state
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
        (burst_calculate_matching_scores.request.id,), countdown=5 + random_delay
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
    if current_caluclation is None:
        return {"status": "done"}

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

    dynamic_template_info, _context = prepare_dynamic_template_context(template_name=template_name, user_id=user.pk)
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
        data={"html": html, "params": _context, "user_id": user.pk, "match_id": None, "subject": subject},
    )

    try:
        from_email = EMAILS_CONFIG.senders["noreply"]
        mail = EmailMessage(
            subject=subject,
            body=html,
            from_email=from_email,
            to=[user.email],
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
def sync_full_user_access_for_manager(manager_user_id: int):
    """
    Mirror all current base-management access grants to a manager user.
    This is intended for users with RECEIVES_FULL_USER_ACCESS.
    """
    from management.controller import get_base_management_user

    manager = User.objects.filter(pk=manager_user_id).first()
    if manager is None:
        return {"status": "manager_not_found", "manager_user_id": manager_user_id}

    if not manager.has_perm(ManagementPermission.RECEIVES_FULL_USER_ACCESS):
        return {"status": "permission_missing", "manager_user_id": manager_user_id}

    base_management_user = get_base_management_user()
    managed_users = base_management_user.managed_users_queryset(active_only=False)

    created_access_grants = 0
    total_processed = 0
    for managed_user in managed_users.iterator():
        total_processed += 1
        if manager.grant_management_access(managed_user, granted_by=base_management_user):
            created_access_grants += 1

    return {
        "status": "ok",
        "manager_user_id": manager_user_id,
        "processed_users": total_processed,
        "created_access_grants": created_access_grants,
    }


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
        if banner.activation_time is not None and banner.activation_time <= current_time:
            banner.active = True
            banner.save()
            bc["activated"].append(banner.pk)

    # 2 - deactivate banners that need deactivation
    p_deactivation_banners = Banner.objects.filter(expiration_time__isnull=False, active=True)

    for banner in p_deactivation_banners:
        if banner.expiration_time is not None and banner.expiration_time <= current_time:
            banner.active = False
            banner.save()
            bc["deactivated"].append(banner.pk)
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
def send_sms_background(self, user_uuid, message):
    """
    Send SMS background task that never retries on failure.
    If the task fails, it should fail permanently to prevent duplicate SMS sending.
    """
    from django.utils import timezone

    from management.controller import get_base_management_user
    from management.models.sms import SmsModel
    from management.models.user import User

    recent_sms = SmsModel.objects.filter(
        recipient__uuid=user_uuid, message=message, created_at__gte=timezone.now() - timezone.timedelta(hours=2)
    ).exists()

    if recent_sms:
        print(f"Skipping duplicate SMS for user {user_uuid} - already sent within last 2 hours")
        return {"status": "skipped", "reason": "duplicate_message"}

    try:
        receipient = User.objects.get(uuid=user_uuid)

        # we only send international 'sms' to prio users
        # This is mianly cause prices are very high, they are per-segment and differnet for every country
        # our sms have 3-10 segemtns, so this get quite expensive quickly
        is_german_number = str(receipient.profile.phone_mobile).startswith("+49")
        if (receipient.state.company not in settings.MATCH_PRIORITY_COMPANIES) and (not is_german_number):
            receipient.sms(
                send_initator=get_base_management_user(),
                message=message,
                dont_send=True,
                skip_reason="Not prio user and not german phone number",
            )
            return {"status": "skipped", "reason": "Not prio user and not german phone number"}

        result = receipient.sms(send_initator=get_base_management_user(), message=message)
        return {"status": "sent", "result": result}
    except Exception as e:
        print(f"SMS task failed for user {user_uuid}: {str(e)}")
        raise  # Re-raise to mark task as failed


@shared_task
def automatic_emails_u023_u024_u025():
    """
    Sends automatic emails to users who have not booked an appointment or completed the self-onboarding after completing the user form.
    """
    from django.conf import settings

    from management.models.pre_matching_appointment import PreMatchingAppointment
    from management.models.profile import Profile
    from management.models.user import User

    def template_for_user_form_reminder(stage: str, user) -> str:
        # u023/u024: distinct copy for volunteers (v) vs learners (l); u025 is still one template.
        if stage in ("u023", "u024"):
            if user.profile.user_type == Profile.TypeChoices.VOLUNTEER:
                return f"automatic-emails-{stage}v"
            return f"automatic-emails-{stage}l"
        return "automatic-emails-u025"

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__U023_U024_U025)

    reminder_stages = [
        ("u023", 3, False, False, False),
        ("u024", 7, True, False, False),
        ("u025", 14, True, True, False),
    ]
    users_sended = []
    for stage, days, three_days_reminder, seven_days_reminder, fourteen_days_reminder in reminder_stages:
        users = (
            User.objects.filter(
                state__user_form_completed_at__lte=dj_timezone.now() - timedelta(days=days),
                state__is_onboarded=False,
                state__user_form_completed_3_days_reminder_send=three_days_reminder,
                state__user_form_completed_7_days_reminder_send=seven_days_reminder,
                state__user_form_completed_14_days_reminder_send=fourteen_days_reminder,
            )
            .filter(
                # Volunteers receive emails regardless of country; learners only if they live in Germany
                Q(profile__user_type=Profile.TypeChoices.VOLUNTEER) | Q(profile__country_of_residence="DE")
            )
            .select_related("profile")
        )
        user_prematching_join = PreMatchingAppointment.objects.filter(user__in=users)
        users = users.exclude(id__in=user_prematching_join.values_list("user", flat=True))

        users_sended.append(users)
        for user in users:
            template = template_for_user_form_reminder(stage, user)
            german_level = list(
                filter(lambda x: x["lang"] == Profile.LanguageChoices.GERMAN, user.profile.lang_skill or [])
            )
            if (not german_level) or (
                german_level and german_level[0]["level"] == Profile.LanguageSkillChoices.LEVEL_0
            ):
                # don't send to too low german level A1 & A2 ( fix: https://github.com/a-little-world/little-world-backend/issues/868 )
                # we still mark the boolean send flag just to ensure that arrent send accidently if this changes
                pass
            else:
                send_email_background.delay(template, user_id=user.pk, emulated_send=emulated_send)
            user.state.set_user_form_completed_reminder_sent(days)

    return {
        "status": "sent",
        "users_u023": users_sended[0],
        "users_u024": users_sended[1],
        "users_u025": users_sended[2],
    }


def _match_journey_matches():
    """Matches that receive the Standard post-confirm email journey.

    Random Call matches share this journey. Temporary in-call matches do not.
    """
    from management.models.matches import Match
    from management.models.unconfirmed_matches import MatchType

    return Match.objects.exclude(match_type=MatchType.TEMPORARY)


def _matches_with_mutual_messages(qs):
    """Matches where each partner has sent the other at least one message *in this match*.

    Scoped to messages from ``first_interaction_at`` onwards. A pair can be matched more than
    once and their ``Chat`` outlives any single match, so an unscoped check reads an earlier
    conversation as this match's first contact and starts the ladder on a match where nobody
    has written yet. ``first_interaction_at`` is stamped in ``update_match_for_message``
    before the ``Message`` row is inserted, so a match's own first message always qualifies.

    First-contact emails (m031–m042) are for this stage only — one-sided chats stay
    on the single-party-contact journey (m023/m024/m025).
    """
    from chat.models import Message
    from django.db.models import Exists, OuterRef

    def sent(sender_field: str, recipient_field: str):
        return Message.objects.filter(
            sender=OuterRef(sender_field),
            recipient=OuterRef(recipient_field),
            created__gte=OuterRef("first_interaction_at"),
        )

    return qs.filter(Exists(sent("user1", "user2")), Exists(sent("user2", "user1")))


#: Days without interaction → the reminder template → the flag that records it was sent.
#: Ordered oldest-first so the stage a match has actually reached is the first one that fits.
INTERACTION_REMINDERS = (
    (14, "automatic-emails-m014", "interaction_reminder_14_days_send"),
    (7, "automatic-emails-m013", "interaction_reminder_7_days_send"),
    (2, "automatic-emails-m012", "interaction_reminder_2_days_send"),
)

M012_M013_M014_LINK = "https://drive.google.com/file/d/1XcY6_OMZES5QJoMkc6jbEzwYNdCWrnaU/view"

#: Result keys the callers and tests read, kept beside the templates they report on.
RESULT_KEY_BY_TEMPLATE = {
    "automatic-emails-m012": "matches_m012",
    "automatic-emails-m013": "matches_m013",
    "automatic-emails-m014": "matches_m014",
}


def _reminder_stage_for(match, now):
    """The one reminder a match is due, or ``None``.

    Chosen by how long the match has been silent, not by walking the flags upwards. The
    flags say what has already been sent; the age says where the match actually is. Reading
    the age first is what stops a match that is *already* past every threshold from
    collecting all three e-mails in one run — see the docstring on the task.
    """
    for days, template, send_field in INTERACTION_REMINDERS:
        if getattr(match, send_field):
            return None  # Already had this stage or a later one; nothing further is due.
        if match.latest_interaction_at is not None and match.latest_interaction_at <= now - timedelta(days=days):
            return days, template, send_field
    return None


@shared_task
def automatic_emails_m012_m013_m014():
    """
    Active match between users but no interaction yet (no messages or video calls).
    Includes matches not yet confirmed by both users (e.g. after proposal accept).
    Applies to Standard and Random Call matches.

    At most one reminder per match per run. The three stages used to be looped in order,
    each selecting on the flag the previous one had just written, so a match already older
    than 14 days matched all three in a single pass: m012 set ``2_days_send``, which let
    m013 select it, which set ``7_days_send``, which let m014 select it. That is invisible
    while matches age through the stages one run at a time, and it fired on 2026-08-27 when
    a batch of months-old Random Call matches entered the query at once — 15 of 17 people
    received all three inside seven seconds.

    Windowing the stages does not fix it: an old match would then match no stage at all,
    because m013 and m014 still require the earlier flags. So the stage is picked by age and
    every earlier flag is marked with it — one e-mail, the one that fits, chain left
    consistent for anything that follows.
    """
    from django.conf import settings

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__M012_M013_M014)

    now = dj_timezone.now()
    candidates = _match_journey_matches().filter(
        active=True,
        total_messages_counter=0,
        total_mutal_video_calls_counter=0,
        latest_interaction_at__isnull=False,
        latest_interaction_at__lte=now - timedelta(days=INTERACTION_REMINDERS[-1][0]),
        support_matching=False,
        # The last stage is terminal, so anything carrying it can never be due again. Pruned
        # in the query rather than in `_reminder_stage_for`, which would otherwise walk every
        # match that has ever been quiet for two days.
        interaction_reminder_14_days_send=False,
    )

    sent = {"matches_m012": [], "matches_m013": [], "matches_m014": []}

    for match in candidates:
        stage = _reminder_stage_for(match, now)
        if stage is None:
            continue
        days, template, send_field = stage

        for user in (match.user1, match.user2):
            send_email_background.delay(
                template,
                user_id=user.id,
                match_id=match.pk,
                emulated_send=emulated_send,
                context={"link_url": M012_M013_M014_LINK},
            )

        # Everything at or below the stage that fired, so a match that arrives late does not
        # walk back down the ladder on later runs.
        changed = [field for threshold, _t, field in INTERACTION_REMINDERS if threshold <= days]
        for field in changed:
            setattr(match, field, True)
        match.save(update_fields=[*changed, "updated_at"])

        # Match objects, not uuids: callers and tests read `.user1` / `.pk` off these.
        sent[RESULT_KEY_BY_TEMPLATE[template]].append(match)

    return {"status": "sent", **sent}


@shared_task
def automatic_emails_m023():
    """
    Notify user when they didn't respond to the first chat message for 3 days.
    Only applies at the start of a conversation - once both users have sent a message, this no longer triggers.
    """
    from chat.models import Chat
    from django.conf import settings
    from django.db.models import Count, F, Min, Q

    from management.models.matches import Match

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__M023)

    chats = (
        Chat.objects.annotate(
            first_message_at=Min("message__created"),
            u1_message_count=Count("message", filter=Q(message__sender=F("u1"))),
            u2_message_count=Count("message", filter=Q(message__sender=F("u2"))),
        )
        .filter(
            first_message_at__lte=dj_timezone.now() - timedelta(days=3),
            three_days_inactive_email_send=False,
        )
        .filter(Q(u1_message_count=0) | Q(u2_message_count=0))
        .exclude(
            Q(u1__is_staff=True)
            | Q(u2__is_staff=True)
            | Q(
                u1__user_permissions__content_type__app_label="management",
                u1__user_permissions__content_type__model="state",
                u1__user_permissions__codename=ManagementPermission.MATCHING_USER.codename,
            )
            | Q(
                u2__user_permissions__content_type__app_label="management",
                u2__user_permissions__content_type__model="state",
                u2__user_permissions__codename=ManagementPermission.MATCHING_USER.codename,
            )
        )
    )
    inactive_chats = []
    for chat in chats:
        first_message = chat.get_messages().order_by("created").first()
        if not first_message:
            continue

        non_responder = chat.u1 if chat.u1_message_count == 0 else chat.u2
        initiator = chat.u2 if non_responder == chat.u1 else chat.u1

        chat.three_days_inactive_email_send = True
        chat.save()
        inactive_chats.append(chat)

        active_match = Match.get_match(initiator, non_responder).order_by("-created_at").first()
        if not active_match:
            continue

        send_email_background.delay(
            "automatic-emails-m023",
            user_id=non_responder.id,
            match_id=active_match.pk,
            emulated_send=emulated_send,
        )

    return {"status": "sent", "inactive_chats": inactive_chats}


@shared_task
def automatic_emails_m024_m025():
    """
    Notify users when one person hasn't responded to the first chat message for 7 days.
    Only applies at the start of a conversation - once both users have sent a message, this no longer triggers.
    """
    from chat.models import Chat
    from django.conf import settings
    from django.db.models import Count, F, Min, Q

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__M024_M025)

    chats = (
        Chat.objects.annotate(
            first_message_at=Min("message__created"),
            u1_message_count=Count("message", filter=Q(message__sender=F("u1"))),
            u2_message_count=Count("message", filter=Q(message__sender=F("u2"))),
        )
        .filter(
            first_message_at__lte=dj_timezone.now() - timedelta(days=7),
            seven_days_inactive_email_send=False,
        )
        .filter(Q(u1_message_count=0) | Q(u2_message_count=0))
        .exclude(
            Q(u1__is_staff=True)
            | Q(u2__is_staff=True)
            | Q(
                u1__user_permissions__content_type__app_label="management",
                u1__user_permissions__content_type__model="state",
                u1__user_permissions__codename=ManagementPermission.MATCHING_USER.codename,
            )
            | Q(
                u2__user_permissions__content_type__app_label="management",
                u2__user_permissions__content_type__model="state",
                u2__user_permissions__codename=ManagementPermission.MATCHING_USER.codename,
            )
        )
    )

    inactive_chats = []

    for chat in chats:
        first_message = chat.get_messages().order_by("created").first()
        if not first_message:
            continue

        non_responder = chat.u1 if chat.u1_message_count == 0 else chat.u2
        initiator = chat.u2 if non_responder == chat.u1 else chat.u1

        chat.seven_days_inactive_email_send = True
        chat.save()
        inactive_chats.append(chat)

        from management.models.matches import Match

        active_match = Match.get_match(initiator, non_responder).order_by("-created_at").first()
        if not active_match:
            continue

        # send email to the user that received the last message
        send_email_background.delay(
            "automatic-emails-m024",
            user_id=non_responder.id,
            match_id=active_match.pk,
            emulated_send=emulated_send,
        )

        # send email to the person that was ghosted
        send_email_background.delay(
            "automatic-emails-m025",
            user_id=initiator.id,
            match_id=active_match.pk,
            emulated_send=emulated_send,
        )

    return {"status": "sent", "inactive_chats": [str(chat.uuid) for chat in inactive_chats]}


@shared_task
def automatic_emails_m031_m032_m033_m042():
    """
    No video call for 7, 14 and 21 days after first chat message or no video call for 30 days after the first interaction.

    Only matches where both partners have sent at least one message (First Contact).
    One-sided chats are handled by m023/m024/m025 instead.
    """
    from django.conf import settings

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__M031_M032_M033_M042)

    # 1 - automatic-emails-m031
    matches_m031 = _matches_with_mutual_messages(_match_journey_matches()).filter(
        active=True,
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
            "automatic-emails-m031", user_id=match.user1.id, match_id=match.pk, emulated_send=emulated_send
        )
        send_email_background.delay(
            "automatic-emails-m031", user_id=match.user2.id, match_id=match.pk, emulated_send=emulated_send
        )

        match.auto_email_m031_send = True
        match.save(update_fields=["auto_email_m031_send", "updated_at"])

    redirect_slugs = {
        "redirect_slug_no": "info-screen",
        "redirect_slug_yes": "match-form1",
    }

    # 2 - automatic-emails-m032
    matches_m032 = _matches_with_mutual_messages(_match_journey_matches()).filter(
        active=True,
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
            match_id=match.pk,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )
        send_email_background.delay(
            "automatic-emails-m032",
            user_id=match.user2.id,
            match_id=match.pk,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )

        match.auto_email_m032_send = True
        match.save(update_fields=["auto_email_m032_send", "updated_at"])

    # 3 - automatic-emails-m033
    matches_m033 = _matches_with_mutual_messages(_match_journey_matches()).filter(
        active=True,
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
            match_id=match.pk,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )
        send_email_background.delay(
            "automatic-emails-m033",
            user_id=match.user2.id,
            match_id=match.pk,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )

        match.auto_email_m033_send = True
        match.save(update_fields=["auto_email_m033_send", "updated_at"])

    # 4 - automatic-emails-m042
    matches_m042 = _matches_with_mutual_messages(_match_journey_matches()).filter(
        active=True,
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
            match_id=match.pk,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )
        send_email_background.delay(
            "automatic-emails-m042",
            user_id=match.user2.id,
            match_id=match.pk,
            emulated_send=emulated_send,
            context=redirect_slugs,
        )

        match.auto_email_m042_send = True
        match.save(update_fields=["auto_email_m042_send", "updated_at"])

    return {
        "status": "sent",
        "matches_m031": matches_m031_uuids,
        "matches_m032": matches_m032_uuids,
        "matches_m033": matches_m033_uuids,
        "matches_m042": matches_m042_uuids,
    }


@shared_task
def automatic_emails_m053_m054_m055():
    """
    Match milestone emails based on weeks since match creation:
    - automatic-emails-m053: 5 weeks after match created (confirmed, active)
    - automatic-emails-m054: 8 weeks after match created (confirmed, active)
    - automatic-emails-m055: 10 weeks after match created (confirmed, active)
    """
    from django.conf import settings
    from emails.api.template_lookup import still_in_contact_yes_url

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__M053_M054_M055)

    redirect_slugs_m053_m055 = {
        "redirect_slug_no": "info-screen",
        "redirect_slug_yes": "match-form1",
    }

    redirect_slugs_m054 = {
        "redirect_slug_no": "info-screen",
        "redirect_slug_yes": "share-story",
    }

    # 1 - automatic-emails-m053
    matches_m053 = _match_journey_matches().filter(
        active=True,
        confirmed=True,
        created_at__lte=dj_timezone.now() - timedelta(weeks=5),
        created_at__gt=dj_timezone.now() - timedelta(weeks=8),
        auto_email_m053_send=False,
        support_matching=False,
    )
    matches_m053_uuids = [str(uuid) for uuid in matches_m053.values_list("uuid", flat=True)]
    for match in matches_m053:
        for user in (match.user1, match.user2):
            send_email_background.delay(
                "automatic-emails-m053",
                user_id=user.id,
                match_id=match.pk,
                emulated_send=emulated_send,
                context={
                    **redirect_slugs_m053_m055,
                    "five_week_survey_url": still_in_contact_yes_url(user, match, redirect_slugs_m053_m055),
                },
            )

        match.auto_email_m053_send = True
        match.save(update_fields=["auto_email_m053_send", "updated_at"])

    # 2 - automatic-emails-m054
    matches_m054 = _match_journey_matches().filter(
        active=True,
        confirmed=True,
        created_at__lte=dj_timezone.now() - timedelta(weeks=8),
        created_at__gt=dj_timezone.now() - timedelta(weeks=10),
        auto_email_m054_send=False,
        support_matching=False,
    )
    matches_m054_uuids = [str(uuid) for uuid in matches_m054.values_list("uuid", flat=True)]
    for match in matches_m054:
        for user in (match.user1, match.user2):
            send_email_background.delay(
                "automatic-emails-m054",
                user_id=user.id,
                match_id=match.pk,
                emulated_send=emulated_send,
                context={
                    **redirect_slugs_m054,
                    "share_story_url": still_in_contact_yes_url(user, match, redirect_slugs_m054),
                },
            )

        match.auto_email_m054_send = True
        match.save(update_fields=["auto_email_m054_send", "updated_at"])

    # 3 - automatic-emails-m055
    matches_m055 = _match_journey_matches().filter(
        active=True,
        confirmed=True,
        created_at__lte=dj_timezone.now() - timedelta(weeks=10),
        auto_email_m055_send=False,
        support_matching=False,
    )
    matches_m055_uuids = [str(uuid) for uuid in matches_m055.values_list("uuid", flat=True)]
    for match in matches_m055:
        for user in (match.user1, match.user2):
            send_email_background.delay(
                "automatic-emails-m055",
                user_id=user.id,
                match_id=match.pk,
                emulated_send=emulated_send,
                context={
                    **redirect_slugs_m053_m055,
                    "completed_match_poll_url": still_in_contact_yes_url(user, match, redirect_slugs_m053_m055),
                },
            )

        match.auto_email_m055_send = True
        match.save(update_fields=["auto_email_m055_send", "updated_at"])

    return {
        "status": "sent",
        "matches_m053": matches_m053_uuids,
        "matches_m054": matches_m054_uuids,
        "matches_m055": matches_m055_uuids,
    }


@shared_task
def automatic_emails_u072_u073_u074():
    """
    TODO: check about u071
    Send for
    automatic-emails-u072: No matching after 10 days
    Trigger: Timing/Trigger: 10 days after #U071#. But still no matching
    automatic-emails-u073: No matching after 21 days
    Trigger: Timing/Trigger: 21 days after #U071#. But still no matching
    automatic-emails-u074: No matching after 30 days
    Trigger: Timing/Trigger: 30 days after #U071#. But still no matching
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
        state__is_onboarded=True,
        state__auto_email_u072_send=False,
        state__has_received_first_match=False,
    )
    users_u072_hashes = list(users_u072.values_list("uuid", flat=True))
    for user in users_u072:
        send_email_background.delay("automatic-emails-u072", user_id=user.pk, emulated_send=emulated_send)
        user.state.auto_email_u072_send = True
        user.state.save()

    users_u073 = User.objects.filter(
        state__onboarding_call_completed_at__lte=dj_timezone.now() - timedelta(days=21),
        state__onboarding_call_completed_at__gt=dj_timezone.now() - timedelta(days=30),
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__is_onboarded=True,
        state__auto_email_u073_send=False,
        state__has_received_first_match=False,
    )
    users_u073_hashes = list(users_u073.values_list("uuid", flat=True))
    for user in users_u073:
        send_email_background.delay("automatic-emails-u073", user_id=user.pk, emulated_send=emulated_send)
        user.state.auto_email_u073_send = True
        user.state.save()

    users_u074 = User.objects.filter(
        state__onboarding_call_completed_at__lte=dj_timezone.now() - timedelta(days=30),
        state__searching_state=State.SearchingStateChoices.SEARCHING,
        state__email_authenticated=True,
        state__unresponsive=False,
        state__is_onboarded=True,
        state__auto_email_u074_send=False,
        state__has_received_first_match=False,
    )
    users_u074_hashes = list(users_u074.values_list("uuid", flat=True))
    for user in users_u074:
        send_email_background.delay("automatic-emails-u074", user_id=user.pk, emulated_send=emulated_send)
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
    User searching again after having a match
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
        state__is_onboarded=True,
        state__auto_emails_u081_send=True,
        state__auto_emails_u082_send=False,
        state__has_received_first_match=True,
    )
    users_u082_hashes = list(users_u082.values_list("uuid", flat=True))
    for user in users_u082:
        send_email_background.delay("automatic-emails-u082", user_id=user.pk, emulated_send=emulated_send)
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
    users_u083_hashes = list(users_u083.values_list("uuid", flat=True))
    for user in users_u083:
        send_email_background.delay("automatic-emails-u083", user_id=user.pk, emulated_send=emulated_send)
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
    users_u084_hashes = list(users_u084.values_list("uuid", flat=True))
    for user in users_u084:
        send_email_background.delay("automatic-emails-u084", user_id=user.pk, emulated_send=emulated_send)
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

    from management.api.slack import notify_communication_channel, notify_security_channel

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
        "AUTOMATIC_EMAILS__M043_M044_M045": {
            "enabled": settings.ENABLE_AUTO_EMAILS__M043_M044_M045,
            "emulated": settings.EMULATE_AUTO_EMAILS__M043_M044_M045,
        },
        "AUTOMATIC_EMAILS__U051_U071": {
            "enabled": settings.ENABLE_AUTO_EMAILS__U051_U071,
            "emulated": settings.EMULATE_AUTO_EMAILS__U051_U071,
        },
        "AUTOMATIC_EMAILS__FM021_FM022": {
            "enabled": settings.ENABLE_AUTO_EMAILS__FM021_FM022,
            "emulated": settings.EMULATE_AUTO_EMAILS__FM021_FM022,
        },
        "AUTOMATIC_EMAILS__M051": {
            "enabled": settings.ENABLE_AUTO_EMAILS__M051,
            "emulated": settings.EMULATE_AUTO_EMAILS__M051,
        },
        "AUTOMATIC_EMAILS__U053_U054": {
            "enabled": settings.ENABLE_AUTO_EMAILS__U053_U054,
            "emulated": settings.EMULATE_AUTO_EMAILS__U053_U054,
        },
        "AUTOMATIC_EMAILS__M053_M054_M055": {
            "enabled": settings.ENABLE_AUTO_EMAILS__M053_M054_M055,
            "emulated": settings.EMULATE_AUTO_EMAILS__M053_M054_M055,
        },
    }

    check_emails = [
        "automatic-emails-u023l",
        "automatic-emails-u023v",
        "automatic-emails-u024l",
        "automatic-emails-u024v",
        "automatic-emails-u025",
        "automatic-emails-u051l",
        "automatic-emails-u051v",
        "automatic-emails-u053l",
        "automatic-emails-u053v",
        "automatic-emails-u054",
        "automatic-emails-u071",
        "automatic-emails-u072",
        "automatic-emails-u073",
        "automatic-emails-u074",
        "automatic-emails-u081",
        "automatic-emails-u082",
        "automatic-emails-u083",
        "automatic-emails-u084",
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
        "automatic-emails-m043",
        "automatic-emails-m044",
        "automatic-emails-m045",
        "automatic-emails-m051",
        "automatic-emails-m053",
        "automatic-emails-m054",
        "automatic-emails-m055",
        "automatic-emails-fm021",
        "automatic-emails-fm022",
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
    # Group users by template for compact per-template breakdown
    template_users = defaultdict(dict)
    unique_user_ids = set()

    for log in email_logs:
        email_counts[log.template] += 1
        if log.receiver:
            template_users[log.template][log.receiver.id] = log.receiver
            unique_user_ids.add(log.receiver.id)

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
    message_parts.append(f"\n*Total:* {total_emails} emails sent to {len(unique_user_ids)} users")

    # Add enabled/disabled and emulated status
    message_parts.append("")
    message_parts.append("*Auto Email Settings:*")
    for setting_name, flags in enabled_emails.items():
        enabled_status = "`True`" if flags["enabled"] else "`False`"
        emulated_status = "`True`" if flags["emulated"] else "`False`"
        message_parts.append(f"• {setting_name}: enabled={enabled_status}, emulated={emulated_status}")

    # Add compact per-template breakdown with user links
    message_parts.append("")
    message_parts.append("*Emails Compact Summary:*")

    def slack_link(url, label):
        return f"<{url}|{label}>"

    for template in check_emails:
        if email_counts.get(template, 0) == 0:
            continue

        template_url = f"{settings.BASE_URL}/matching/emails/{template}"
        users_for_template = template_users.get(template, {})
        user_links = " ".join(
            slack_link(f"{settings.BASE_URL}/matching/user/{user.id}?tab=emails", user.id)
            for user in sorted(users_for_template.values(), key=lambda u: u.id)
        )
        message_parts.append(f"- {slack_link(template_url, template)} - {user_links or 'no users'}")

    message = "\n".join(message_parts)
    notify_security_channel(message)
    notify_communication_channel(message)

    return {
        "status": "sent",
        "date": yesterday_start.strftime("%Y-%m-%d"),
        "total_emails": total_emails,
        "unique_users": len(unique_user_ids),
        "email_counts": dict(email_counts),
    }


@shared_task
def daily_sms_report():
    from collections import defaultdict
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from management.api.slack import notify_communication_channel, notify_security_channel
    from management.models.sms import SmsModel

    now = timezone.now()
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = yesterday_start + timedelta(days=1)

    sms_logs = SmsModel.objects.filter(created_at__gte=yesterday_start, created_at__lt=yesterday_end).select_related(
        "recipient", "send_initator"
    )

    if not sms_logs.exists():
        message = f"*SMS Report:* ({yesterday_start.strftime('%Y-%m-%d')})\n\nNo SMS were sent yesterday."
        notify_security_channel(message)
        return {"status": "no_sms", "date": yesterday_start.strftime("%Y-%m-%d")}

    total_sms = sms_logs.count()
    successful_sms = sms_logs.filter(success=True).count()
    failed_sms = total_sms - successful_sms

    recipient_sms = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})
    initiator_sms = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})

    for sms in sms_logs:
        if sms.recipient:
            recipient_sms[sms.recipient]["total"] += 1
            if sms.success:
                recipient_sms[sms.recipient]["success"] += 1
            else:
                recipient_sms[sms.recipient]["failed"] += 1

        if sms.send_initator:
            initiator_sms[sms.send_initator]["total"] += 1
            if sms.success:
                initiator_sms[sms.send_initator]["success"] += 1
            else:
                initiator_sms[sms.send_initator]["failed"] += 1

    message_parts = [
        f"*SMS Report:* ({yesterday_start.strftime('%Y-%m-%d')})",
        "",
        f"*Summary:* total={total_sms}, success={successful_sms}, failed={failed_sms}",
        f"*Unique Users:* recipients={len(recipient_sms)}, initiators={len(initiator_sms)}",
        "",
        "*SMS Per-Recipient:*",
    ]

    for recipient, counts in sorted(recipient_sms.items(), key=lambda x: x[0].email if x[0] else ""):
        if recipient:
            user_url = f"{settings.BASE_URL}/matching/user/{recipient.id}?tab=emails"
            message_parts.append(
                "• "
                + f"{recipient.email}: total={counts['total']}, success={counts['success']}, failed={counts['failed']} "
                + f"- `{user_url}`"
            )

    message_parts.append("")
    message_parts.append("*SMS Per-Initiator:*")
    for initiator, counts in sorted(initiator_sms.items(), key=lambda x: x[0].email if x[0] else ""):
        if initiator:
            user_url = f"{settings.BASE_URL}/matching/user/{initiator.id}?tab=emails"
            message_parts.append(
                "• "
                + f"{initiator.email}: total={counts['total']}, success={counts['success']}, failed={counts['failed']} "
                + f"- `{user_url}`"
            )

    message = "\n".join(message_parts)
    notify_security_channel(message)
    notify_communication_channel(message)

    return {
        "status": "sent",
        "date": yesterday_start.strftime("%Y-%m-%d"),
        "total_sms": total_sms,
        "successful_sms": successful_sms,
        "failed_sms": failed_sms,
        "unique_recipients": len(recipient_sms),
        "unique_initiators": len(initiator_sms),
    }


@shared_task
def automatic_emails_m043_m044_m045():
    """
    Implements after 5, 8, 10 Video Calls Match Emails
    and the
    - [`automatic-emails-m043`](https://little-world.com/matching/emails/automatic-emails-m043) after 5 video calls, send once
    - [`automatic-emails-m044`](https://little-world.com/matching/emails/automatic-emails-m044) after 8 video calls, send once
    - [`automatic-emails-m045`](https://little-world.com/matching/emails/automatic-emails-m045) after 10 video calls, send once
    TODO
    - [ ] Add correct form urls...
    """
    from django.conf import settings
    from django.utils import timezone

    from management.models.matches import sync_match_counters_for_queryset
    from management.models.profile import Profile

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.ENABLE_AUTO_EMAILS__M043_M044_M045)

    def _video_call_survey_url(user):
        if user.profile.user_type == Profile.TypeChoices.LEARNER:
            return settings.GOOGLE_FORM_COMPLETED_X_VIDEO_CALLS_LEARNER
        return settings.GOOGLE_FORM_COMPLETED_X_VIDEO_CALLS_VOLUNTEER

    report = {
        "counters_synced_m043": 0,
        "counters_synced_m044": 0,
        "counters_synced_m045": 0,
        "m043_send_to": [],
        "m044_send_to": [],
        "m045_send_to": [],
    }

    # Counters are synced before this task
    time_1week_ago = timezone.now() - timedelta(days=7)
    from django.db.models import F

    # 1 - Sync counters
    # === 10 x Video Calls ===
    sync__matches_video_call_m045 = _match_journey_matches().filter(
        active=True,
        confirmed=True,
        auto_email_m043_send=True,
        auto_email_m044_send=True,
        auto_email_m045_send=False,
        latest_counter_sync__lte=F("latest_interaction_at"),
    )

    synced_m045 = sync_match_counters_for_queryset(sync__matches_video_call_m045)
    report["counters_synced_m045"] += synced_m045

    matches_video_call_m045 = _match_journey_matches().filter(
        active=True,
        confirmed=True,
        auto_email_m043_send=True,
        auto_email_m044_send=True,
        auto_email_m045_send=False,
        completed_5_video_calls=True,
        completed_8_video_calls=True,
        completed_10_video_calls=True,
        latest_interaction_at__gte=time_1week_ago,
    )

    # Send 10 x Video Call Emails
    for match in matches_video_call_m045:
        for user in (match.user1, match.user2):
            send_email_background.delay(
                "automatic-emails-m045",
                user_id=user.id,
                match_id=match.pk,
                emulated_send=emulated_send,
                context={"share_story_url": _video_call_survey_url(user)},
            )
            report["m045_send_to"].append([str(match.uuid), user.id])
        match.auto_email_m043_send = True
        match.auto_email_m044_send = True
        match.auto_email_m045_send = True
        match.completed_10_video_calls = True
        match.save(
            update_fields=[
                "auto_email_m043_send",
                "auto_email_m044_send",
                "auto_email_m045_send",
                "completed_10_video_calls",
                "updated_at",
            ]
        )

    # === 8 x Video Calls ===
    sync__matches_video_call_m044 = _match_journey_matches().filter(
        active=True,
        confirmed=True,
        auto_email_m043_send=True,
        auto_email_m044_send=False,
        auto_email_m045_send=False,
        latest_counter_sync__lte=F("latest_interaction_at"),
    )

    synced_m044 = sync_match_counters_for_queryset(sync__matches_video_call_m044)
    report["counters_synced_m044"] += synced_m044

    matches_video_call_m044 = _match_journey_matches().filter(
        active=True,
        confirmed=True,
        auto_email_m043_send=True,
        auto_email_m044_send=False,
        auto_email_m045_send=False,
        completed_5_video_calls=True,
        completed_8_video_calls=True,
        completed_10_video_calls=False,
        latest_interaction_at__gte=time_1week_ago,
    )

    # Send 8x Video Call Emails
    for match in matches_video_call_m044:
        # uses share_story_url internally automaticly
        send_email_background.delay(
            "automatic-emails-m044", user_id=match.user1.id, match_id=match.pk, emulated_send=emulated_send
        )
        send_email_background.delay(
            "automatic-emails-m044", user_id=match.user2.id, match_id=match.pk, emulated_send=emulated_send
        )
        report["m044_send_to"].append([str(match.uuid), match.user1.id])
        report["m044_send_to"].append([str(match.uuid), match.user2.id])
        match.auto_email_m043_send = True
        match.auto_email_m044_send = True
        match.completed_5_video_calls = True
        match.completed_8_video_calls = True
        match.save(
            update_fields=[
                "auto_email_m043_send",
                "auto_email_m044_send",
                "completed_5_video_calls",
                "completed_8_video_calls",
                "updated_at",
            ]
        )

    # === 5 x Video Calls ===
    # Only check matches where latest_counter_sync <= latest_interaction_at
    sync__matches_video_call_m043 = _match_journey_matches().filter(
        active=True,
        confirmed=True,
        auto_email_m043_send=False,
        auto_email_m044_send=False,
        auto_email_m045_send=False,
        latest_counter_sync__lte=F("latest_interaction_at"),
    )

    synced_m043 = sync_match_counters_for_queryset(sync__matches_video_call_m043)
    report["counters_synced_m043"] += synced_m043

    matches_video_call_m043 = _match_journey_matches().filter(
        active=True,
        confirmed=True,
        auto_email_m043_send=False,
        auto_email_m044_send=False,
        auto_email_m045_send=False,
        completed_5_video_calls=True,
        completed_8_video_calls=False,
        completed_10_video_calls=False,
        latest_interaction_at__gte=time_1week_ago,
    )

    # Send 5x Video Call Emails
    for match in matches_video_call_m043:
        for user in (match.user1, match.user2):
            send_email_background.delay(
                "automatic-emails-m043",
                user_id=user.id,
                emulated_send=emulated_send,
                context={"post_videocall_survey_url": _video_call_survey_url(user)},
            )
            report["m043_send_to"].append([str(match.uuid), user.id])
        match.auto_email_m043_send = True
        match.completed_5_video_calls = True
        match.save(update_fields=["auto_email_m043_send", "completed_5_video_calls", "updated_at"])

    return report


@shared_task
def automatic_emails_u051_u071():
    """
    u051: send if user did not attend onboarding call
    u071: send if user did attend onboarding call
    """
    from management.models.profile import Profile

    def template_for_u051(user: User) -> str:
        if user.profile.user_type == Profile.TypeChoices.VOLUNTEER:
            return "automatic-emails-u051v"
        return "automatic-emails-u051l"

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__U051_U071)

    users_u071 = User.objects.filter(
        is_active=True,
        state__is_onboarded=True,
        state__onboarding_call_completed_at__isnull=False,
        state__attended_auto_email_u071_send=False,
    )
    users_u071_hashes = list(users_u071.values_list("uuid", flat=True))
    for user in users_u071:
        send_email_background.delay("automatic-emails-u071", user_id=user.pk, emulated_send=emulated_send)
        if not emulated_send:
            send_push_notification(user, "push_notification.onboarding_completed", path="/app")
        user.state.attended_auto_email_u071_send = True
        user.state.attended_auto_email_u071_send_at = dj_timezone.now()
        user.state.save()

    users_u051 = User.objects.filter(
        is_active=True,
        state__is_onboarded=False,
        state__last_prematching_call_not_attended=True,
        state__last_not_attended_prematching_call_at__isnull=False,
        state__not_attended_auto_email_u051_send=False,
    )
    users_u051_hashes = list(users_u051.values_list("uuid", flat=True))
    for user in users_u051:
        send_email_background.delay(template_for_u051(user), user_id=user.pk, emulated_send=emulated_send)
        user.state.not_attended_auto_email_u051_send = True
        user.state.not_attended_auto_email_u051_send_at = dj_timezone.now()
        user.state.save()

    return {
        "status": "sent",
        "u051_count": len(users_u051_hashes),
        "u051_users": users_u051_hashes,
        "u071_count": len(users_u071_hashes),
        "u071_users": users_u071_hashes,
    }


@shared_task
def automatic_emails_u053_u054():
    """
    Implements automatic emails for not attending pre-matching appointments.
    u053: send if at least 2 days passed since missed appointment
    u054: send if at least 7 days passed since missed appointment (follow-up to u053)
    """
    from django.conf import settings
    from django.utils import timezone

    from management.models.profile import Profile

    def template_for_u053(user: User) -> str:
        if user.profile.user_type == Profile.TypeChoices.VOLUNTEER:
            return "automatic-emails-u053v"
        return "automatic-emails-u053l"

    def push_notification_key_for_u053(user: User) -> str:
        if user.profile.user_type == Profile.TypeChoices.VOLUNTEER:
            return "push_notification.missed_onboarding_volunteer"
        return "push_notification.missed_onboarding_learner"

    time_2days_ago = timezone.now() - timedelta(days=2)
    time_7days_ago = timezone.now() - timedelta(days=7)

    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.ENABLE_AUTO_EMAILS__U053_U054)

    users_missed_onboarding = User.objects.filter(
        is_active=True,
        state__last_prematching_call_not_attended=True,
        state__last_not_attended_prematching_call_at__lte=time_2days_ago,
        state__not_attended_auto_email_u053_send=False,
        state__not_attended_auto_email_u054_send=False,
        state__is_onboarded=False,
    ).select_related("profile")

    users_with_new_appointment = set()
    for user in users_missed_onboarding:
        has_new_appointment = PreMatchingAppointment.objects.filter(
            user=user,
            start_time__gte=user.state.last_not_attended_prematching_call_at,
        ).exists()
        if has_new_appointment:
            users_with_new_appointment.add(user.pk)

    user_missed_last_onboarding_u053 = users_missed_onboarding.exclude(id__in=users_with_new_appointment)

    users_missed_onboarding_u054 = User.objects.filter(
        is_active=True,
        state__last_prematching_call_not_attended=True,
        state__last_not_attended_prematching_call_at__lte=time_7days_ago,
        state__not_attended_auto_email_u053_send=True,
        state__not_attended_auto_email_u054_send=False,
        state__is_onboarded=False,
    )

    users_with_new_appointment_u054 = set()
    for user in users_missed_onboarding_u054:
        has_new_appointment = PreMatchingAppointment.objects.filter(
            user=user,
            start_time__gte=user.state.last_not_attended_prematching_call_at,
        ).exists()
        if has_new_appointment:
            users_with_new_appointment_u054.add(user.pk)

    user_missed_last_onboarding_u054 = users_missed_onboarding_u054.exclude(id__in=users_with_new_appointment_u054)

    u053_hashes = []
    for user in user_missed_last_onboarding_u053:
        send_email_background.delay(
            template_for_u053(user),
            user_id=user.pk,
            emulated_send=emulated_send,
        )
        if not emulated_send:
            send_push_notification(user, push_notification_key_for_u053(user), path="/app/onboarding")
        user.state.not_attended_auto_email_u053_send = True
        user.state.not_attended_auto_email_u053_send_at = timezone.now()
        user.state.save()
        u053_hashes.append(str(user.uuid))

    u054_hashes = []
    for user in user_missed_last_onboarding_u054:
        send_email_background.delay("automatic-emails-u054", user_id=user.pk, emulated_send=emulated_send)
        user.state.not_attended_auto_email_u054_send = True
        user.state.not_attended_auto_email_u054_send_at = timezone.now()
        user.state.save()
        u054_hashes.append(str(user.uuid))

    report = {
        "status": "sent",
        "u053_count": len(u053_hashes),
        "u053_users": u053_hashes,
        "u054_count": len(u054_hashes),
        "u054_users": u054_hashes,
        "excluded_new_appointment_u053": len(users_with_new_appointment),
        "excluded_new_appointment_u054": len(users_with_new_appointment_u054),
    }

    return report


def _get_unreplied_message_streak(messages):
    """
    From newest-first messages, find the trailing one-sided streak: consecutive
    messages from the same sender at the end with no reply from the other party.

    Returns (last_message, unreplied_since) where unreplied_since is when that
    streak started, or (None, None) if there are no messages.
    """
    messages = list(messages)
    if not messages:
        return None, None

    last_message = messages[0]
    unreplied_since = last_message.created
    last_sender_id = last_message.sender_id

    for message in messages[1:]:
        if message.sender_id != last_sender_id:
            break
        unreplied_since = message.created

    return last_message, unreplied_since


@shared_task
def automatic_emails_fm021_fm022__ghosted_matches():
    """
    Implements automatic emails for 15 days single party contact
    sends 2 different emails:
    - [ ] [`automatic-emails-fm021`](https://little-world.com/matching/emails/automatic-emails-fm021) to the ghoster
    - [ ] [`automatic-emails-fm022`](https://little-world.com/matching/emails/automatic-emails-fm022) to the ghosted
    """
    from chat.models import Message
    from django.conf import settings
    from django.utils import timezone
    from video.models import LivekitSession

    from management.api.report_unmatch import process_report_unmatch
    from management.match_success import successful_match_ids

    time_15days_ago = timezone.now() - timedelta(days=15)
    time_3weeks_ago = timezone.now() - timedelta(weeks=3)
    emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__FM021_FM022)

    report = {
        "matches_single_party_contact": 0,
        "matches_ghosted": [],
        "fm021_send_to": [],
        "fm022_send_to": [],
    }
    # Matches that started interacting in the last 3 weeks & haven't had a mutual video call
    matches_in_ko_with_single_party_contact = (
        _match_journey_matches()
        .filter(
            active=True,
            completed=False,  # dont even consider removing completed matches!
            completed_off_plattform=False,
            support_matching=False,
            auto_email_fm021_send=False,
            auto_email_fm022_send=False,
            is_ghosted_match=False,
            total_mutal_video_calls_counter=0,
            user1__is_active=True,
            user2__is_active=True,
        )
        .exclude(first_interaction_at__lt=time_3weeks_ago)
    )

    # Exclude successful matches - this task unmatches, so a false positive here
    # removes a working pair.
    #
    # Both routes to success are covered: `completed_off_plattform=False` in the filter
    # above excludes off-platform completions, and this excludes anything at or over the
    # token threshold.
    matches_in_ko_with_single_party_contact = matches_in_ko_with_single_party_contact.exclude(
        id__in=successful_match_ids(matches_in_ko_with_single_party_contact)
    )

    # Check if matches should be marked 'ghosted'
    # TODO: confirm if there should be a way to get out of 'ghosted' state
    report["matches_single_party_contact"] = matches_in_ko_with_single_party_contact.count()
    for match in matches_in_ko_with_single_party_contact:
        messages = Message.objects.filter(
            Q(sender=match.user1, recipient=match.user2) | Q(sender=match.user2, recipient=match.user1)
        ).order_by("-created")
        last_message, unreplied_since = _get_unreplied_message_streak(messages)
        had_mutual_video_call = LivekitSession.objects.filter(
            Q(u1=match.user1, u2=match.user2) | Q(u1=match.user2, u2=match.user1),
            both_have_been_active=True,
        ).exists()
        if (
            last_message
            and unreplied_since is not None
            and unreplied_since < time_15days_ago
            and not had_mutual_video_call
        ):
            match.is_ghosted_match = True
            ghosted_user = last_message.sender
            ghosted_by_user = last_message.recipient
            match.ghosted_by = ghosted_by_user
            match.marked_as_ghosted_at = timezone.now()
            match.save(update_fields=["is_ghosted_match", "ghosted_by", "marked_as_ghosted_at", "updated_at"])
            report["matches_ghosted"].append(match.uuid)
            send_email_background.delay(
                "automatic-emails-fm021", user_id=ghosted_user.id, match_id=match.pk, emulated_send=emulated_send
            )
            send_email_background.delay(
                "automatic-emails-fm022", user_id=ghosted_by_user.id, match_id=match.pk, emulated_send=emulated_send
            )
            report["fm021_send_to"].append([str(match.uuid), ghosted_user.id])
            report["fm022_send_to"].append([str(match.uuid), ghosted_by_user.id])
            match.auto_email_fm021_send = True
            match.auto_email_fm022_send = True
            match.save(update_fields=["auto_email_fm021_send", "auto_email_fm022_send", "updated_at"])
            # We actually remove the matching and mark it as 'ghosted'
            process_report_unmatch(
                match.user1, match, "ghosted", "Single party contact for 15 days", send_message=False
            )

    return {"status": "sent", "matches": matches_in_ko_with_single_party_contact}


def _scrub_survey_free_text(user):
    """Strip free-text survey answers for a deleted account.

    Ratings are anonymous once the account is scrubbed and stay in aggregates, but a comment
    can name a person or an employer. Which keys are free text is a property of the campaign,
    so the question set decides rather than a hardcoded field name.
    """
    from management.models.survey import SurveyResponse

    responses = SurveyResponse.objects.filter(user=user).select_related("campaign")
    scrubbed = []
    for response in responses:
        text_ids = [qid for qid in response.campaign.text_question_ids() if qid in response.answers]
        if not text_ids:
            continue
        for qid in text_ids:
            del response.answers[qid]
        scrubbed.append(response)
    if scrubbed:
        SurveyResponse.objects.bulk_update(scrubbed, ["answers"])
    return len(scrubbed)


@shared_task(name="management.tasks.cleanup_deleted_users_full_user_data")
def cleanup_deleted_users_full_user_data(days_since_deletion: int = 30):
    from management.models.user import User

    cutoff_date = dj_timezone.now() - timedelta(days=days_since_deletion)
    users = User.objects.filter(
        is_active=False,
        state__deleted_at__isnull=False,
        state__deleted_at__lt=cutoff_date,
        state__deleted_full_user_data_cleared=False,
    ).select_related("profile", "state")

    processed_user_ids = []
    for user in users.iterator():
        # Remove data that can include personal content or contact details.
        user.first_name = "deleted"
        user.last_name = ""
        user.email = f"deleted_user_{user.pk}@deleted.local"
        user.username = user.email
        user.set_unusable_password()
        user.save(update_fields=["first_name", "last_name", "email", "username", "password"])

        profile = user.profile
        if profile.image:
            profile.image.delete(save=False)
        profile.first_name = "Ghost"
        profile.second_name = "User"
        profile.postal_code = ""
        profile.phone_mobile = ""
        profile.description = ""
        profile.language_skill_description = ""
        profile.additional_interests = ""
        profile.job_skill_description = ""
        profile.other_target_group = ""
        profile.availability = {}
        profile.avatar_config = {}
        profile.image_type = profile.ImageTypeChoice.AVATAR
        profile.save()

        # Before the state flag: a user marked cleared is never revisited, so a scrub that
        # failed after the flag was written would leave the free text in place forever.
        _scrub_survey_free_text(user)

        state = user.state
        state.notes = ""
        state.past_emails = []
        state.deleted_full_user_data_cleared = True
        state.save()

        processed_user_ids.append(user.pk)

    return {
        "processed_users_count": len(processed_user_ids),
        "processed_user_ids": processed_user_ids,
        "cutoff_date": cutoff_date.isoformat(),
    }


@shared_task
def push_notification_background(user_id: int, **kwargs):
    user = User.objects.get(pk=user_id)
    if user:
        user.push_notification(**kwargs)


def send_push_notification(user: User, translation_key: str, path: str | None = None):
    user.push_notification(
        title=get_translation(f"{translation_key}.title", lang="de"),
        description=get_translation(f"{translation_key}.description", lang="de"),
        notification_type=PushNotificationType.ANNOUNCEMENT,
        path=path,
    )


@shared_task
def onboarding_call_reminder_push_notification(user_id: int):
    """Reminder push for the onboarding call, scheduled (eta) one hour before the call (see u044)."""
    user = User.objects.filter(pk=user_id).first()
    if user is None or not user.is_active:
        return
    appointment = PreMatchingAppointment.objects.filter(user=user).first()
    if appointment is None:
        return
    # the appointment may have been rebooked after this task was scheduled
    if not (timedelta(0) <= appointment.start_time - dj_timezone.now() <= timedelta(hours=1, minutes=5)):
        return
    send_push_notification(user, "push_notification.onboarding_call_reminder", path="/app/onboarding/")
