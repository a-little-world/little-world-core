"""
This is a controller for any userform related actions
e.g.: Creating a new user, sending a notification to a users etc...
"""
from chat.django_private_chat2.consumers.message_types import MessageTypes, OutgoingEventNewTextMessage
from chat.django_private_chat2.models import DialogsModel
from asgiref.sync import async_to_sync
from back.utils import _double_uuid
from channels.layers import get_channel_layer
from .models import User
from django.conf import settings
from .models import UserSerializer, User, Profile, State, Settings, Room
from django.utils.translation import gettext_lazy as _
from emails import mails
from tracking import utils
from tracking.models import Event
import os


class UserNotFoundErr(Exception):
    pass


# All models *every* user should have!
user_models = {  # Model, primary key name
    "user": [User, 'email'],
    "profile": [Profile, 'user'],
    "state": [State, 'user'],
    "settings": [Settings, 'settings']
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
    except User.DoesNotExist as e:
        # We should throw an error if a user was looked up that doesn't exist
        # If this error occurs we most likely forgot to delte the user from someones matches
        # But we still allow this to be caught with 'try' and returned as a parsed error
        raise UserNotFoundErr(_("User doesn't exist"))


def get_user_by_email(email):
    return __user_get_catch(email=email)


def get_user_by_hash(hash) -> User:
    # TODO: here i'm assuming that .get return only one object and throws an error if there are multiple
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
        elem = user_models[k][0].objects.get(
            user=user) if k != "user" else user
        d[k] = elem
    return d


def create_user(
    email,
    password,
    first_name,
    second_name,
    birth_year,
    send_verification_mail=True
):
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
        password=password
    )
    user_data_serializer = UserSerializer(data=data)  # type: ignore

    # If you don't want this to error catch serializers.ValidationError!
    user_data_serializer.is_valid(raise_exception=True)
    # The user_data_serializer automaticly creates the user model
    # automaticly creates Profile, State, Settings, see models.user.UserManager
    data['last_name'] = data.pop('second_name')
    usr = User.objects.create_user(**data)
    # Error if user doesn't exist, would prob already happen on is_valid
    assert isinstance(usr, User)

    # Step 4 send mail
    if send_verification_mail:
        try:
            verifiaction_url = f"{settings.BASE_URL}/api/user/verify/email/{usr.state.get_email_auth_code_b64()}"
            mails.send_email(
                recivers=[email],
                subject="undefined",  # TODO set!
                mail_data=mails.get_mail_data_by_name("welcome"),
                mail_params=mails.WelcomeEmailParams(
                    first_name=usr.profile.first_name,
                    verification_url=verifiaction_url,
                    verification_code=str(usr.state.get_email_auth_pin())
                )
            )
        except:
            # TODO: actualy return an error and log this
            print("Email sending failed!")
    else:
        print("Not sending verification mail!")

    # Step 5 Match with admin user
    # Do *not* send an matching mail, or notification or message!
    # Also no need to set the admin user as unconfirmed,
    # there is no popup message required about being matched to the admin!
    match_users({get_base_management_user(), usr},
                send_notification=False,
                send_message=False,
                send_email=False,
                set_unconfirmed=False)

    # Step 6 Create a room for the two users!
    # This allowes them to authenticate twilio rooms for video calls
    # TODO

    # Step 7 Notify the user
    # TODO set title, description & co...
    usr.notify(title=_("Welcome Notification"))

    # Step 8 Message the user from the admin account
    usr.message(_("Welcome Message..."))
    return usr


# 'set' No one can put two identical users
@utils.track_event(
    name="Users Matched",
    event_type=Event.EventTypeChoices.FLOW,
    tags=["backend", "function", "db"])
def match_users(
        users: set,
        send_notification=True,
        send_message=True,
        send_email=True,
        create_dialog=True,
        create_video_room=True,
        set_unconfirmed=True):
    """ Accepts a list of two users to match """
    from chat.django_private_chat2.models import DialogsModel

    assert len(users) == 2, f"Accepts only two users! ({', '.join(users)})"
    usr1, usr2 = list(users)
    usr1.match(usr2, set_unconfirmed=set_unconfirmed)
    usr2.match(usr1, set_unconfirmed=set_unconfirmed)

    if create_dialog:
        # After the users are registered as matches
        # we still need to create a dialog for them
        DialogsModel.create_if_not_exists(usr1, usr2)

    if create_video_room:
        room = Room.objects.create(
            usr1=usr1,
            usr2=usr2
        )

    if send_notification:
        usr1.notify(title=_("New match: %s" % usr2.profile.first_name))
        usr2.notify(title=_("New match: %s" % usr1.profile.first_name))

    if send_message:
        # Sends a message from the admin model
        usr1.message(_("New match found! Checkout %s's profile now" %
                     usr2.profile.first_name))
        usr2.message(_("New match found! Checkout %s's profile now" %
                     usr1.profile.first_name))

    if send_email:
        usr1.send_email(
            subject="undefined",  # TODO set!
            mail_data=mails.get_mail_data_by_name("match"),
            mail_params=mails.MatchMailParams(
                first_name=usr1.profile.first_name,
                match_first_name=usr2.profile.first_name,
                profile_link_url=settings.BASE_URL  # TODO
            )
        )
        usr2.send_email(
            subject="undefined",  # TODO set!
            mail_data=mails.get_mail_data_by_name("match"),
            mail_params=mails.MatchMailParams(
                first_name=usr2.profile.first_name,
                match_first_name=usr1.profile.first_name,
                # TODO: should be the actual profile slug in the future
                profile_link_url=settings.BASE_URL
            )
        )


def unmatch_users(users: set):
    """ Accepts a list of two users to unmatch """
    assert len(users) == 2, f"Accepts only two users! ({', '.join(users)})"
    # Un-Match ... TODO


def get_base_management_user():
    """
    Always returns the BASE_MANAGEMENT_USER user
    """
    try:
        return get_user_by_email(settings.MANAGEMENT_USER_MAIL)
    except UserNotFoundErr:
        return create_base_admin_and_add_standart_db_values()


def create_base_admin_and_add_standart_db_values():
    print("Management user doesn't seem to exist jet")
    usr = User.objects.create_superuser(
        email=settings.MANAGEMENT_USER_MAIL,
        username=settings.MANAGEMENT_USER_MAIL,
        password=os.environ['DJ_MANAGEMENT_PW'],
        first_name=os.environ.get(
            'DJ_MANAGEMENT_FIRST_NAME', 'Oliver (Support)'),
        second_name=os.environ.get(
            'DJ_MANAGEMENT_SECOND_NAME', ''),
    )
    usr.state.set_user_form_completed()  # Admin doesn't have to fill the userform
    usr.notify("You are the admin master!")
    print("BASE ADMIN USER CREATED!")

    # Now we create some default database elements that should be part of all setups!
    from management.tasks import (
        create_default_community_events,
        create_default_cookie_groups,
        fill_base_management_user_profile,
        create_default_table_score_source
    )

    # Create default cookie groups and community events
    # This is done as celery task in the background!
    create_default_cookie_groups.delay()
    create_default_community_events.delay()
    fill_base_management_user_profile.delay()
    create_default_table_score_source.delay()

    return usr


def send_websocket_callback(
        to_usr,
        message: str,
        from_user=None):
    """
    This sends a websocket chat message without saving it 
    this can be used for simple frontend callbacks 
    such as there is a twilio call incomming!
    """
    if not from_user:
        from_user = get_base_management_user()

    assert from_user.is_staff
    admin = from_user

    channel_layer = get_channel_layer()
    dialog = DialogsModel.dialog_exists(admin, to_usr)
    async_to_sync(channel_layer.group_send)(str(to_usr.pk), {
        "type": "send_message_dialog_def",
        "dialog_id": str(to_usr.pk),
        "message": f"[TMPADMIN]({message})]",
        "admin_pk": str(admin.pk),
        "user_pk": str(to_usr.pk),
        "admin_h256_pk": str(admin.hash),
    })

# TODO: can this cause issues when settings not initalized?


def send_chat_message(to_user, from_user, message):
    """
    This can send a chat message from any user to any user
    this is intended to the used by the BASE_MANAGEMENT_USER
    so usualy the from_user would be 'get_base_management_user'
    """
    # Send a chat message ... TODO
    pass
