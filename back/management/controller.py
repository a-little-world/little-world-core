"""
This is a controller for any userform related actions
e.g.: Creating a new user, sending a notification to a users etc...
"""

from django.utils import timezone
from management.models.management_tasks import MangementTask
from django.db.models import Q
from django.db import transaction
from typing import Dict, Callable
from management.models.unconfirmed_matches import ProposedMatch
from management.models.past_matches import PastMatch
from management.models.matches import Match
from management import controller
from dataclasses import dataclass
from django.conf import settings
from management.models.user import UserSerializer, User
from management.models.profile import Profile
from management.models.state import State
from management.models.settings import Settings
from management.models.rooms import Room
from management.models.scores import TwoUserMatchingScore
from chat.models import Chat
from emails import mails
from translations import get_translation
import os
from management.tasks import (
    create_default_banners,
    create_default_community_events,
    create_default_cookie_groups,
    fill_base_management_user_tim_profile,
)


class UserNotFoundErr(Exception):
    pass


# All models *every* user should have!
user_models = {  # Model, primary key name
    "user": [User, "email"],
    "profile": [Profile, "user"],
    "state": [State, "user"],
    "settings": [Settings, "settings"],
}


def get_user(user, lookup="email"):
    """
    Three ways to look up a user: email, hash or pk
    pk is obviously the fastest, but generaly we shouldn't have to care
    we could also add some neat indexing here to speed up further
    """
    if lookup == "email":
        return get_user_by_email(user)
    elif lookup == "hash":
        return get_user_by_hash(user)
    elif lookup == "pk":
        return get_user_by_pk(user)
    else:
        raise Exception(f"lookup '{lookup}' doesn't exist ")


def __user_get_catch(**kwargs):
    try:
        return User.objects.get(**kwargs)
    except User.DoesNotExist:
        # We should throw an error if a user was looked up that doesn't exist
        # If this error occurs we most likely forgot to delete the user from someones matches
        # But we still allow this to be caught with 'try' and returned as a parsed error
        raise UserNotFoundErr("User doesn't exist")


def get_user_by_email(email):
    return __user_get_catch(email=email)


def get_user_by_hash(hash) -> User:
    return __user_get_catch(hash=hash)


# We accept string input, but this will error if its not convertable to int
def get_user_by_pk(pk):
    pk = int(pk)
    # we use .get with primary key so we will always get only one user
    return __user_get_catch(id=pk)


def get_user_models(user):
    # We don't need to catch any user not found erros,
    # cause you need to first get the usr and that should be done with get_user_*
    d = {}
    for k in user_models:
        elem = user_models[k][0].objects.get(user=user) if k != "user" else user
        d[k] = elem
    return d


def send_still_active_question_message(user):
    user.message(get_translation("auto_messages.are_you_still_in_contact", lang="de").format(first_name=user.first_name), auto_mark_read=False)


def make_tim_support_user(user, old_management_mail="littleworld.management@gmail.com", send_message=True, custom_message=None):
    # 1. We need to remove oliver as matching user

    admin_user = controller.get_user_by_email(old_management_mail)
    old_support_matching = Match.get_match(user1=admin_user, user2=user)
    if old_support_matching.exists():
        unmatch_users({admin_user, user}, unmatcher=admin_user)

    # 2. make the new admin matching
    base_management_user = get_base_management_user()

    match_users({base_management_user, user}, send_notification=False, send_message=False, send_email=False, set_unconfirmed=False)

    # 2.5 add that user to the managed users by Tim
    base_management_user.state.managed_users.add(user)
    base_management_user.state.save()

    # 3. set that user to 'not searching'
    us = user.state
    us.still_active_reminder_send = True
    us.searching_state = State.SearchingStateChoices.IDLE
    us.save()

    # 4. send the 'still active' question message
    if send_message:
        if custom_message is not None:
            user.message(custom_message, auto_mark_read=False)
        else:
            send_still_active_question_message(user)


def create_user(email, password, first_name, second_name, birth_year, company=None, newsletter_subscribed=False, send_verification_mail=True, send_welcome_notification=True):
    """
    This should be used when creating a new user, it may throw validations errors!
    performs the following setps:
    Note: this assumes some rought validations steps where done already, see `api.register.Register`
    1 - validate for user model
    1.5 - validate for profile model (implicit cause only first_name, second_name, birth_year are needed right now )
    3 - create all models <- happens automaticly when the user model is created, see management.models.user.UserManager
    4 - send email verification code
    5 - create welcome notification
    6 - send welcome message from admin chat
    """
    # Step 1 - 3
    data = dict(
        # Currently we don't allow any specific username
        username=email,  # NOTE that if we change mail we need to change 'username' too
        email=email,
        first_name=first_name,
        second_name=second_name,
        password=password,
    )
    user_data_serializer = UserSerializer(data=data)  # type: ignore

    # If you don't want this to error catch serializers.ValidationError!
    user_data_serializer.is_valid(raise_exception=True)
    # The user_data_serializer automaticly creates the user model
    # automaticly creates Profile, State, Settings, see models.user.UserManager
    data["last_name"] = data.pop("second_name")
    usr = User.objects.create_user(**data)

    usr.profile.birth_year = int(birth_year)
    usr.profile.newsletter_subscribed = newsletter_subscribed
    usr.profile.save()

    # Error if user doesn't exist, would prob already happen on is_valid
    assert isinstance(usr, User)

    # Step 3.5 - Check if the user has a 'comany' field
    if company is not None:
        usr.state.company = company
        usr.state.save()

    # Step 4 send mail
    if send_verification_mail:

        def send_verify_link():
            usr.send_email_v2("welcome")

        send_verify_link()

    base_management_user = get_base_management_user()

    # Step 5 Match with admin user
    # Do *not* send an matching mail, or notification or message!
    # Also no need to set the admin user as unconfirmed,
    # there is no popup message required about being matched to the admin!
    matching = match_users({base_management_user, usr}, send_notification=False, send_message=False, send_email=False, set_unconfirmed=False)

    print("Created Match:", matching.user1.email, "<->", matching.user2.email, "(support)" if matching.support_matching else "")

    if not base_management_user.is_staff:
        # At the moment all our users get the same management user
        # in the future there might be a process to assign different management users to different users
        base_management_user.state.managed_users.add(usr)
        base_management_user.state.save()

    return usr

def match_users(users: set, send_notification=True, send_message=True, send_email=True, create_dialog=True, create_video_room=True, create_livekit_room=True, set_unconfirmed=True, set_to_idle=True):
    """Accepts a list of two users to match"""

    assert len(users) == 2, f"Accepts only two users! ({', '.join(users)})"
    usr1, usr2 = list(users)

    # Only match if they are not already matched!
    matching = Match.get_match(usr1, usr2)
    if matching.exists():
        # Before we raise the exception we check for 'dangeling' matches
        from management.models.unconfirmed_matches import ProposedMatch

        dangeling = ProposedMatch.get_proposal_between(usr1, usr2)
        if dangeling.exists():
            dangeling.delete()
            raise Exception("Users are already matched, but dangeling proposals found, DELETED!")

        raise Exception("Users are already matched!")

    # It can also be a support matching with a 'management' user
    is_support_matching = (usr1.is_staff or usr2.is_staff) or (usr1.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER) or usr2.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER))

    # This is the new way:
    matching_obj = Match.objects.create(
        user1=usr1,
        user2=usr2,
        confirmed=is_support_matching,  # if support matching always confimed = true prevents it from showing up in 'unconfirmed' initally
        support_matching=is_support_matching,
    )

    if create_livekit_room:
        from video.models import LiveKitRoom

        if not (LiveKitRoom.objects.filter(Q(u1=usr1, u2=usr2) | Q(u1=usr2, u2=usr1)).exists()):
            LiveKitRoom.objects.create(
                u1=usr1,
                u2=usr2,
            )

    if create_dialog:
        # After the users are registered as matches
        # we still need to create a dialog for them

        chat = Chat.get_or_create_chat(usr1, usr2)

    if create_video_room:
        room = Room.objects.create(usr1=usr1, usr2=usr2)

    if send_notification:
        pass # TODO: send notification should be used to trigger an SMS notification

    if send_message:
        match_message = get_translation("auto_messages.match_message", lang="de")

        # Sends a message from the admin model
        usr1.message(match_message.format(other_name=usr2.profile.first_name), auto_mark_read=True)
        usr2.message(match_message.format(other_name=usr1.profile.first_name), auto_mark_read=True)

    if send_email:
        usr1.send_email_v2("new-match", match_id=matching_obj.id)
        usr2.send_email_v2("new-match", match_id=matching_obj.id)

    if set_to_idle:
        usr1.state.set_idle()
        usr2.state.set_idle()

    # If there was a two user matching score we need to set it to matchable=False now as the users are matched
    # & also ofcourse all other scores of that users have to be set to matchable=False
    TwoUserMatchingScore.objects.filter((Q(user1=usr1) | Q(user2=usr1) | Q(user1=usr2) | Q(user2=usr2)) & Q(matchable=True)).update(matchable=False)

    return matching_obj


def create_user_matching_proposal(users: set, send_confirm_match_email=True):
    """
    This represents the new intermediate matching step we created.
    Users are not just matched directly but first a matching proposal is send to the 'learner' user.
    """
    u1, u2 = list(users)
    proposal = ProposedMatch.objects.create(
        user1=u1,
        user2=u2,
        # When this is faulse the create signal will not send an email!
        send_inital_mail=(not send_confirm_match_email),
    )
    return proposal


def unmatch_users(users: set, delete_video_room=True, delete_dialog=True, unmatcher=None):
    """
    Accepts a list of two users to unmatch

    Do:
    - Remove both from respective 'matches' field
    Need to delete:
    - Dialog
    - Messages ( or set to `deleted` )
    - Video Room
    """
    assert len(users) == 2, f"Accepts only two users! ({', '.join(users)})"

    # Un-Match the users by removing the from their 'matches' field

    if unmatcher is None:
        unmatcher = get_base_management_user()

    usr1, usr2 = list(users)

    # The new match management strategy
    match = Match.get_match(usr1, usr2)
    assert match.exists(), "Match does not exist!"
    match = match.first()
    match.active = False
    match.report_unmatch.append({
        "kind": "unmatch",
        "reason": "Manual User unmatch Matching pannel",
        "match_id": match.id,
        "time": str(timezone.now()),
        "user_id": unmatcher.pk if unmatcher else "no unmatcher specified",
        "user_uuid": unmatcher.hash if unmatcher else "no unmatcher specified",
    })
    match.save()

    # Then disable the video room
    if delete_video_room:
        from .models.rooms import get_rooms_match

        get_rooms_match(usr1, usr2).delete()

    return PastMatch.objects.create(user1=usr1, user2=usr2, who_unmatched=unmatcher)


def get_base_management_user():
    """
    Always returns the BASE_MANAGEMENT_USER user
    """

    TIM_MANAGEMENT_USER_MAIL = "tim.timschupp+420@gmail.com"
    try:
        return get_user_by_email(TIM_MANAGEMENT_USER_MAIL)
    except UserNotFoundErr:
        return create_base_admin_and_add_standart_db_values()


def get_or_create_default_docs_user():
    if not settings.CREATE_DOCS_USER:
        return None
    if not settings.DOCS_USER:
        raise Exception("DOCS_USER not set!")
    if not settings.DOCS_PASSWORD:
        raise Exception("DOCS_USER_PW not set!")

    user = None
    try:
        return get_user_by_email(settings.DOCS_USER)
    except UserNotFoundErr:
        create_user(
            email=settings.DOCS_USER, password=settings.DOCS_PASSWORD, first_name="Docs", second_name="User", birth_year=2000, newsletter_subscribed=False, send_verification_mail=False, send_welcome_notification=False
        )

    def finish_up_user_creation():
        user = get_user_by_email(settings.DOCS_USER)
        user.state.email_authenticated = True
        user.state.extra_user_permissions.append(State.ExtraUserPermissionChoices.DOCS_VIEW)
        user.state.extra_user_permissions.append(State.ExtraUserPermissionChoices.API_SCHEMAS)
        user.state.extra_user_permissions.append(State.ExtraUserPermissionChoices.AUTO_LOGIN)
        user.state.auto_login_api_token = settings.DOCS_USER_LOGIN_TOKEN
        user.state.save()
        user.state.set_user_form_completed()

    transaction.on_commit(finish_up_user_creation)

    return get_user_by_email(settings.DOCS_USER)


def create_base_admin_and_add_standart_db_values():
    try:
        get_user_by_email(settings.MANAGEMENT_USER_MAIL)
    except UserNotFoundErr:
        usr = User.objects.create_superuser(
            email=settings.MANAGEMENT_USER_MAIL,
            username=settings.MANAGEMENT_USER_MAIL,
            password=os.environ["DJ_MANAGEMENT_PW"],
            first_name=os.environ.get("DJ_MANAGEMENT_FIRST_NAME", "Oliver (Support)"),
            second_name=os.environ.get("DJ_MANAGEMENT_SECOND_NAME", ""),
        )
        usr.state.email_authenticated = True
        usr.state.save()
        usr.state.set_user_form_completed()  # Admin doesn't have to fill the userform
        print("Base Admin User: Newly created!")

    def update_profile():
        usr_tim = get_user_by_email(TIM_MANAGEMENT_USER_MAIL)
        usr_tim.state.extra_user_permissions.append(State.ExtraUserPermissionChoices.MATCHING_USER)
        usr_tim.state.email_authenticated = True
        usr_tim.state.save()
        usr_tim.state.set_user_form_completed()  # Admin doesn't have to fill the userform

    # Tim Schupp is the new base admin user, we will now create a match with hin instead:
    TIM_MANAGEMENT_USER_MAIL = "tim.timschupp+420@gmail.com"
    try:
        usr_tim = get_user_by_email(TIM_MANAGEMENT_USER_MAIL)
    except UserNotFoundErr:
        usr_tim = User.objects.create_user(
            email="tim.timschupp+420@gmail.com",
            username="tim.timschupp+420@gmail.com",
            password=os.environ["DJ_TIM_MANAGEMENT_PW"],
            first_name="Tim",
            last_name="Schupp",
        )
        print(f"Base Management user {usr_tim.email} newly created!")

    transaction.on_commit(update_profile)
    # The tim user should always get the matching permission

    # Now we create some default database elements that should be part of all setups!

    # Create default cookie groups and community events
    # This is done as celery task in the background!
    create_default_cookie_groups.delay()
    create_default_community_events.delay()
    create_default_banners.delay()
    fill_base_management_user_tim_profile.delay()

    get_or_create_default_docs_user()

    return usr_tim


@dataclass
class EmailSendReport:
    send: bool = False
    checked_subscription: bool = False
    subscription_group: str = "none"
    unsubscribable: bool = False
    unsubscribed: bool = False
    out: str = ""


def send_email(
    user,
    subject: str,
    mail_name: str,
    mail_params_func: Callable,
    unsubscribe_group=None,
    emulated_send=False,
):
    # TODO: remove with the migration to new email apis
    if settings.DISABLE_LEGACY_EMAIL_SENDING:
        raise Exception("Legacy email sending is disabled!")

    report = EmailSendReport()
    settings_hash = str(user.settings.email_settings.hash)

    mail_params = mail_params_func(user)

    if unsubscribe_group is not None:
        unsub_link = f"https://little-world.com/api/emails/toggle_sub/?choice=False&unsubscribe_type={unsubscribe_group}&settings_hash={settings_hash}"
        mail_params.unsubscribe_url1 = unsub_link
        report.checked_subscription = True
        report.subscription_group = unsubscribe_group

        if user.settings.email_settings.has_unsubscribed(unsubscribe_group):
            print(f"User ({user.email}) has unsubscribed from", unsubscribe_group)
            report.unsubscribed = True
            return report
    else:
        report.checked_subscription = False

    try:
        mails.send_email(
            recivers=[user.email],
            subject=subject,
            mail_data=mails.get_mail_data_by_name(mail_name),
            mail_params=mail_params,
            raise_exception=True,
            emulated_send=emulated_send,
        )
        report.send = not emulated_send
    except Exception as e:
        print("Error sending email", str(e), mail_name)
        report.send = False
        report.out += f"Error sending email: {e}" + str(e)

    return report


def send_group_mail(
    users,
    subject: str,
    mail_name: str,
    mail_params_func: Callable,
    unsubscribe_group=None,
    debug=False,
    # 'emulated_send' Allows to just petend sending a mail, will create a email log etc but **not** send the actuall email!
    emulated_send=False,
):
    reports: Dict[str, EmailSendReport] = {}

    total = len(users)
    if debug:
        print(f"Sending {total} bluk emails")
    i = 0
    for user in users:
        i += 1
        if debug:
            print(f"Sending email ({i}/{total}) to {user.email}")
        reports[user.hash] = send_email(
            user,
            subject,
            mail_name,
            mail_params_func,
            unsubscribe_group=unsubscribe_group,
            emulated_send=emulated_send,
        )

    return reports


def delete_user(user, management_user=None, send_deletion_email=False):
    from emails import mails

    if send_deletion_email:
        if settings.USE_V2_EMAIL_APIS:
            user.send_email_v2("account-deleted")
        else:
            user.send_email(
                subject="Dein Account wurde gelöscht",
                mail_data=mails.get_mail_data_by_name("account_deleted"),
                mail_params=mails.AccountDeletedEmailParams(
                    first_name=user.profile.first_name,
                ),
            )

    user.is_active = False
    user.email = f"deleted_{user.email}"
    user.first_name = "deleted"
    user.set_unusable_password()
    user.save()

    task = MangementTask.create_task(user=user, description="Cleanup user delete data", management_user=management_user)
    user.state.management_tasks.add(task)
    user.state.save()

    user.profile.first_name = f"deleted, {user.profile.first_name}"
    user.profile.second_name = f"deleted, {user.profile.second_name}"
    user.profile.image_type = Profile.ImageTypeChoice.AVATAR
    user.profile.avatar_config = {}
    user.profile.phone_mobile = f"deleted, {user.profile.phone_mobile}"
    user.profile.save()
