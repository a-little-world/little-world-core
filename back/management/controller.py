"""
This is a controller for any userform related actions
e.g.: Creating a new user, sending a notification to a users etc...
"""
import urllib.parse
from uuid import uuid4
from django.utils import translation
from django.db import transaction
from typing import Dict, Callable
from management.models.unconfirmed_matches import UnconfirmedMatch
from management.models.backend_state import BackendState
from management.models.past_matches import PastMatch
from management.models.matches import Match
from chat_old.django_private_chat2.models import DialogsModel
from management import controller
from dataclasses import dataclass, fields, field
from chat_old.django_private_chat2.consumers.message_types import MessageTypes, OutgoingEventNewTextMessage
from chat_old.django_private_chat2.models import DialogsModel, MessageModel
from django.utils import timezone
from asgiref.sync import async_to_sync
from back.utils import _double_uuid
from channels.layers import get_channel_layer
from django.conf import settings
from management.models.user import UserSerializer, User
from management.models.profile import Profile
from management.models.state import State
from management.models.settings import Settings
from management.models.rooms import Room
from chat.models import Chat
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from emails import mails
from tracking import utils
from tracking.models import Event
import json
import os
from management.tasks import (
    create_default_community_events,
    create_default_cookie_groups,
    fill_base_management_user_tim_profile,
)


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

def send_still_active_question_message(user):
    user.message(pgettext_lazy("api.are-you-still-searching", """Hallo {first_name}, ich bin Tim, Mitbegründer und CTO von Little World!

Entschuldige, dass du warten musstest. Wir überarbeiten gerade einige Dinge an unserer Plattform und unserem Matching-Verfahren. Ich bin dein neuer Support-Nutzer und werde dir bei allen Fragen und Problemen helfen.

Da du dich schon vor einiger Zeit registriert hast, wollte ich dich fragen, ob du noch aktiv auf der Suche bist? Antworte mir gerne mit einer schnellen Nachricht oder drücke kurz auf diesen Knopf: <a href="/user/still_active/">Ich suche noch ein Match!</a>

Solange du auf dein Match wartest, kannst du dir schon mal den <a href="https://home.little-world.com/leitfaden">Gesprächsleitfaden</a> anschauen. Hier findest du viele hilfreiche Tipps und Antworten auf mögliche Fragen.

Viele Grüße aus Aachen 👋🏼""".format(first_name=user.first_name)), auto_mark_read=False)


def make_tim_support_user(
        user, 
        old_management_mail="littleworld.management@gmail.com", 
        send_message=True,
        custom_message=None
    ):
    # 1. We need to remove oliver as matching user
    
    admin_user = controller.get_user_by_email(old_management_mail)
    old_support_matching = Match.get_match(user1=admin_user, user2=user)
    if old_support_matching.exists():
        controller.unmatch_users({admin_user, user}, unmatcher=admin_user)
        
    # 2. make the new admin matching
    base_management_user = get_base_management_user()
    
    match_users({ base_management_user, user },
                send_notification=False,
                send_message=False,
                send_email=False,
                set_unconfirmed=False)
    
    # 2.5 add that user to the managed users by Tim
    base_management_user.state.managed_users.add(user)
    base_management_user.state.save()
    
    # 3. set that user to 'not searching'
    us = user.state
    us.still_active_reminder_send = True
    us.matching_state = State.MatchingStateChoices.IDLE
    us.save()
    
    # 4. send the 'still active' question message
    if send_message:
        if not (custom_message is None):
            user.message(custom_message, auto_mark_read=False)
        else:
            send_still_active_question_message(user)



def create_user(
    email,
    password,
    first_name,
    second_name,
    birth_year,
    newsletter_subscribed=False,
    send_verification_mail=True,
    send_welcome_notification=True,
    send_welcome_message=True,
    catch_email_send_errors=True,
    check_prematching_invitations=False
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

    usr.profile.birth_year = int(birth_year)
    usr.profile.newsletter_subscribed = newsletter_subscribed
    usr.profile.save()
    # Error if user doesn't exist, would prob already happen on is_valid
    assert isinstance(usr, User)

    # Step 4 send mail
    if send_verification_mail:
        def send_verify_link():
            link_route = 'mailverify_link'  # api/user/verify/email
            verifiaction_url = f"{settings.BASE_URL}/{link_route}/{usr.state.get_email_auth_code_b64()}"
            mails.send_email(
                recivers=[email],
                subject=pgettext_lazy(
                    "api.register-welcome-mail-subject", "{code} - Verifizierungscode zur E-Mail Bestätigun".format(code=usr.state.get_email_auth_pin())),
                mail_data=mails.get_mail_data_by_name("welcome"),
                mail_params=mails.WelcomeEmailParams(
                    first_name=usr.profile.first_name,
                    verification_url=verifiaction_url,
                    verification_code=str(usr.state.get_email_auth_pin())
                )
            )
        if catch_email_send_errors:
            try:
                send_verify_link()
            except Exception as e:
                print("Email sending failed!" + str(e))
        else:
            send_verify_link()
    else:
        print("Not sending verification mail!")

    base_management_user = get_base_management_user()
    
    matching = match_users({ base_management_user, usr },
                send_notification=False,
                send_message=False,
                send_email=False,
                set_unconfirmed=False)
    
    print("Created matching", matching,"is_support:", matching.support_matching)

    if not base_management_user.is_staff:
        # Must be a mather user now TODO
        # Add that user to the list of users managed by this management user!
        base_management_user.state.managed_users.add(usr)
        base_management_user.state.save()

    # Step 5 Match with admin user
    # Do *not* send an matching mail, or notification or message!
    # Also no need to set the admin user as unconfirmed,
    # there is no popup message required about being matched to the admin!
    
    # TODO: since this was just updated and we now have 'matcher' users
    # this doesn't always have to be the same management user anymore
    # Generay how we handle management users needs to be significantly improved!

    # Step 7 Notify the user
    if send_welcome_notification:
        usr.notify(title=_("Welcome Notification"))

    # Step 8 Message the user from the admin account
    if send_welcome_message:

        default_message = pgettext_lazy("api.register-welcome-message-text", """Hallo {first_name} und herzlich willkommen bei Little World!

Ich bin Tim, Mitbegründer und CTO von Little World. Danke, dass du ein Teil unserer Plattform geworden bist!

Aktuell arbeiten wir an einigen Aktualisierungen unserer Plattform und unseres Matching-Verfahrens und schätzen daher jedes <a href="/app/help">Feedback</a>, das wir von dir erhalten.

Während wir für dich ein passendes Match finden, kannst du gerne in unserem <a href="https://home.little-world.com/leitfaden">Gesprächsleitfaden</a> stöbern. Hier findest du viele hilfreiche Tipps und Antworten auf mögliche Fragen.

Vielen Dank im Voraus für deine Hilfe und herzlichste Grüße aus Aachen!""".format(first_name=first_name))
            
    if check_prematching_invitations:
        # Now we need to check the prematching state
        # TODO: there is a bug here if the user decides to change the email, then the booking will be made from the wrong email.
        
        default_message = pgettext_lazy("api.register-invite-pre-match-interview", """Hallo {first_name} und herzlich willkommen bei Little World!

Ich bin Tim, Mitbegründer und CTO von Little World. Danke, dass du ein Teil unserer Plattform geworden bist!

Aktuell arbeiten wir an einigen Aktualisierungen unserer Plattform und unseres Matching-Verfahrens und schätzen daher jedes Feedback, das wir von dir erhalten. Du kannst deine Gedanken und Erfahrungen jederzeit über diesen Link mit uns teilen: <a href="/app/help">Feedback</a>.

Bevor es richtig losgeht, musst du einen 15-minütigen Videocall-Termin mit mir vereinbaren. In diesem Gespräch werden wir gemeinsam deine Suchangaben überprüfen, und ich werde dir die nächsten Schritte zur Teilnahme bei Little World erklären. Bitte buche dafür einen Termin in dem folgenden Kalender: <button data-cal-link="{calcom_meeting_id}?{encoded_params}"  data-cal-config='{{"layout":"month_view"}}'>Buche ein Meeting</button>.

Während wir für dich ein passendes Match finden, kannst du gerne in unserem Gesprächsleitfaden unter diesem Link stöbern: <a href="https://home.little-world.com/leitfaden">Gesprächsleitfaden</a>. Hier findest du viele hilfreiche Tipps und Antworten auf mögliche Fragen.

Vielen Dank im Voraus für deine Hilfe und herzlichste Grüße aus Aachen!""".format(first_name=first_name,encoded_params=urllib.parse.urlencode({
            "email": str(usr.email),
            "hash": str(usr.hash),
            "bookingcode": str(usr.state.prematch_booking_code)
        }), 
        hash=usr.hash,
        calcom_meeting_id=settings.DJ_CALCOM_MEETING_ID))

        usr.state.require_pre_matching_call = True
        usr.state.save()
        
    usr.message(default_message, auto_mark_read=True)
    
    return usr


def are_users_matched(
    users: set
):
    assert len(users) == 2, f"Accepts only two users! ({', '.join(users)})"
    usr1, usr2 = list(users)
    
    # TODO: need updating to the new Match model relation!
    return usr1.is_matched(usr2) and usr2.is_matched(usr1)


def match_users(
        users: set,
        send_notification=True,
        send_message=True,
        send_email=True,
        create_dialog=True,
        create_video_room=True,
        set_unconfirmed=True,
        set_to_idle=True):
    """ Accepts a list of two users to match """

    assert len(users) == 2, f"Accepts only two users! ({', '.join(users)})"
    usr1, usr2 = list(users)
    
    # Only match if they are not already matched!
    matching = Match.get_match(usr1, usr2)
    if matching.exists():
        # Before we raise the exception we check for 'dangeling' matches 
        from management.models.unconfirmed_matches import UnconfirmedMatch
        dangeling = UnconfirmedMatch.get_proposal_between(usr1, usr2)
        if dangeling.exists():
            dangeling.delete()
            raise Exception("Users are already matched, but dangeling proposals found, DELETED!")

        raise Exception("Users are already matched!")
    
    # TODO: this is the old way to match to be removed one our frontend strategy updated
    # For now we deploy both ways and make then work along side, but the old-way is to be removed asap
    usr1.match(usr2, set_unconfirmed=set_unconfirmed)
    usr2.match(usr1, set_unconfirmed=set_unconfirmed)
    
    # It can also be a support matching with a 'management' user
    is_support_matching = (usr1.is_staff or usr2.is_staff) \
        or (usr1.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER) or \
            usr2.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER))
    
    # This is the new way:
    matching_obj = Match.objects.create(
        user1=usr1,
        user2=usr2,
        confirmed=is_support_matching, # if support matching always confimed = true prevents it from showing up in 'unconfirmed' initally 
        support_matching=is_support_matching
    )

    if create_dialog:
        # After the users are registered as matches
        # we still need to create a dialog for them
        
        chat = Chat.get_or_create_chat(usr1, usr2)
        
        # TODO: old depricated way to create dialog:
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
        with translation.override("en"):
            match_message = pgettext_lazy("api.match-made-message-text", """Glückwunsch, wir haben jemanden für dich gefunden! 

    Am besten vereinbarst du direkt einen Termin mit {other_name} für euer erstes Gespräch – das klappt meist besser als viele Nachrichten. 
    Unterhalten könnt ihr euch zur vereinbarten Zeit auf Little World indem du oben rechts auf das Anruf-Symbol drückt. 
    Schau dir gerne schon vorher das Profil von {other_name} an, indem du auf den Namen drückst. 

    Damit euch viel Spaß! Schöne Grüße vom Team Little World""")
        # Sends a message from the admin model
        usr1.message(match_message.format(
            other_name=usr2.profile.first_name), auto_mark_read=True)
        usr2.message(match_message.format(
            other_name=usr1.profile.first_name), auto_mark_read=True)

    if send_email:
        usr1.send_email(
            subject=pgettext_lazy(
                "api.match-made-email-subject", "Glückwunsch! Gesprächspartner:in gefunden auf Little World"),
            mail_data=mails.get_mail_data_by_name("match"),
            mail_params=mails.MatchMailParams(
                first_name=usr1.profile.first_name,
                match_first_name=usr2.profile.first_name,
                profile_link_url=settings.BASE_URL
            )
        )
        usr2.send_email(
            subject=pgettext_lazy(
                "api.match-made-email-subject", "Glückwunsch! Gesprächspartner:in gefunden auf Little World"),
            mail_data=mails.get_mail_data_by_name("match"),
            mail_params=mails.MatchMailParams(
                first_name=usr2.profile.first_name,
                match_first_name=usr1.profile.first_name,
                # TODO: should be the actual profile slug in the future
                profile_link_url=settings.BASE_URL
            )
        )

    if set_to_idle:
        usr1.state.set_idle()
        usr2.state.set_idle()
        
    return matching_obj


def create_user_matching_proposal(
    users: set,
    send_confirm_match_email=True
):
    """
    This represents the new intermediate matching step we created.
    Users are not just matched directly but first a matching proposal is send to the 'volunteer' user. 
    TODO or is it the learner im still not sure on this?
    """
    u1, u2 = list(users)
    proposal = UnconfirmedMatch.objects.create(
        user1=u1,
        user2=u2,
        # When this is faulse the create signal will not send an email!
        send_inital_mail=(not send_confirm_match_email)
    )
    return proposal

def unmatch_users(
    users: set,
    delete_video_room=True,
    delete_dialog=True,
    unmatcher=None
):
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

    # TODO: old strategy, to be removed
    usr1, usr2 = list(users)
    usr1.unmatch(usr2)
    usr2.unmatch(usr1)
    
    # The new match management strategy
    match = Match.get_match(usr1, usr2)
    assert match.exists(), "Match does not exist!"
    match = match.first()
    match.active = False
    match.save()

    # Then disable the video room
    if delete_video_room:
        from .models.rooms import get_rooms_match
        get_rooms_match(usr1, usr2).delete()

    # Delte the dialog
    if delete_dialog:
        from chat_old.django_private_chat2.models import DialogsModel
        dia = DialogsModel.dialog_exists(usr1, usr2)
        if dia:
            dia.delete()

    return PastMatch.objects.create(
        user1=usr1,
        user2=usr2,
        who_unmatched=unmatcher
    )


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
            email=settings.DOCS_USER,
            password=settings.DOCS_PASSWORD,
            first_name="Docs",
            second_name="User",
            birth_year=2000,
            newsletter_subscribed=False,
            send_verification_mail=False,
            send_welcome_notification=False,
            send_welcome_message=False,
            catch_email_send_errors=False,
            check_prematching_invitations=False
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
    print("Management user doesn't seem to exist jet")

    try:
        get_user_by_email(settings.MANAGEMENT_USER_MAIL)
    except UserNotFoundErr:
        usr = User.objects.create_superuser(
            email=settings.MANAGEMENT_USER_MAIL,
            username=settings.MANAGEMENT_USER_MAIL,
            password=os.environ['DJ_MANAGEMENT_PW'],
            first_name=os.environ.get(
                'DJ_MANAGEMENT_FIRST_NAME', 'Oliver (Support)'),
            second_name=os.environ.get(
                'DJ_MANAGEMENT_SECOND_NAME', ''),
        )
        usr.state.email_authenticated = True
        usr.state.save()
        usr.state.set_user_form_completed()  # Admin doesn't have to fill the userform
        usr.notify("You are the admin master!")
    print("BASE ADMIN USER CREATED!")
    
    def update_profile():
        usr_tim = get_user_by_email(TIM_MANAGEMENT_USER_MAIL)
        usr_tim.state.extra_user_permissions.append(State.ExtraUserPermissionChoices.MATCHING_USER)
        usr_tim.state.email_authenticated = True
        usr_tim.state.save()
        usr_tim.state.set_user_form_completed()  # Admin doesn't have to fill the userform
        usr_tim.notify("You are the bese management user with less permissions.")
    
    # Tim Schupp is the new base admin user, we will now create a match with hin instead:
    TIM_MANAGEMENT_USER_MAIL = "tim.timschupp+420@gmail.com"
    try:
        usr_tim = get_user_by_email(TIM_MANAGEMENT_USER_MAIL)
    except UserNotFoundErr:
        usr_tim = User.objects.create_user(
            email="tim.timschupp+420@gmail.com",
            username="tim.timschupp+420@gmail.com",
            password=os.environ['DJ_TIM_MANAGEMENT_PW'],
            first_name="Tim",
            last_name="Schupp",
        )
        
    transaction.on_commit(update_profile)
        # The tim user should always get the matching permission

    print("TIM ADMIN USER CREATED!")
    
    # Now we create some default database elements that should be part of all setups!

    # Create default cookie groups and community events
    # This is done as celery task in the background!
    create_default_cookie_groups.delay()
    create_default_community_events.delay()
    fill_base_management_user_tim_profile.delay()
    
    get_or_create_default_docs_user()

    return usr_tim


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

    assert (from_user.is_staff or from_user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER))
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


def send_chat_message(to_user, from_user, message):
    """
    This can send a chat message from any user to any user
    this is intended to the used by the BASE_MANAGEMENT_USER
    so usualy the from_user would be 'get_base_management_user'
    """
    # Send a chat message ... TODO
    pass

def extract_user_activity_info(user):
    """
    A general function to generate an overview of a users activity
    
    email-verified: XX
    user-type: XX
    email-changes: XX
    from-finished: XX
    user-searching: XX
    logins-total: XX
    matches-total (past & present): XX
    currnet-matches: XX
    messages-send-total: XX
    last-activity: XX days ago
    
    matches:
        last-time-active: XX
        match-messages-total: XX
        
        TODO: we can sorta measure this but extracting this infor is resource intensive
        video-calls-total: XX

    """
    
    # TODO: normally we would also want to check how many actually sucessfull attempts the user did

    login_event_count = Event.objects.filter(
        tags__contains=["frontend", "login", "sensitive"], 
        type=Event.EventTypeChoices.REQUEST, 
        name="User Logged in",
        caller=user
    ).count()
    
    def get_match_tag(u1, u2):
        if u1.pk == u2.pk:
            print("User matched with self", u1.email, u2.email)
            return False
        if(u1.pk > u2.pk):
            return f"match-{u2.pk}-{u1.pk}"
        else:
            return f"match-{u1.pk}-{u2.pk}"
        
    MATCH_DATA = {}
    def add_match_data(u1, u2, data):
        match_tag = get_match_tag(u1, u2)
        if not match_tag in MATCH_DATA:
            MATCH_DATA[match_tag] = {**data}
        else:
            MATCH_DATA[match_tag] = {**MATCH_DATA[match_tag], **data} 
        
    
    user_dialogs = DialogsModel.get_dialogs_for_user_as_object(user)
    total_messages = 0

    current_time = timezone.now()

    for dialog in user_dialogs:
        other_user = dialog.user1 if dialog.user1 != user else dialog.user2
        if get_match_tag(user, other_user):
            message_count = MessageModel.get_message_count_for_dialog_with_user(dialog.user1, dialog.user2)
            last_message = MessageModel.get_last_message_object_for_dialog(dialog.user1, dialog.user2)
            first_message = MessageModel.get_first_message_object_for_dialog(dialog.user1, dialog.user2)
            add_match_data(user, other_user, {
                "match_messages_total": message_count,
            })
            if first_message:
                add_match_data(user, other_user, {
                    "first_message": str(first_message.created) + f" ({first_message.created - current_time} days ago)",
                })
            if last_message:
                add_match_data(user, other_user, {
                    "last_message" : str(last_message.created) + f" ({last_message.created - current_time} days ago)",
                })
            total_messages += message_count
        
    data = {
        "email" : user.email,
        "first_name": user.profile.first_name,
        "email_verified": user.state.email_authenticated,
        "email_changes": len(user.state.past_emails),
        "user_type": user.profile.user_type,
        "form_finished": user.state.user_form_state == State.UserFormStateChoices.FILLED,
        "user_searching": user.state.matching_state,
        "logins_total": login_event_count,
        # TODO: there is actually no goodway to measure amount of past matches
        # "matches_total": user.matches.count() - 1, # - default match
        # TODO: the matches count calculation needs to be updated with the new user model
        "current_matches": user.state.matches.count(),
        "messages_send_total": total_messages,
        "match_activity": MATCH_DATA,
    }
    #print(json.dumps(data, indent=2, default=str))
    return data

        
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
        report.send = (not emulated_send)
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
        i+=1
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

