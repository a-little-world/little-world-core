from .admin_panel_v2 import IsAdminOrMatchingUser
from back.utils import _api_url
from django.urls import path, re_path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from management.twilio_handler import _get_client

default_tim_management_changed_message = """
Hallo {first_name}, ich bin Tim, Mitbegründer und CTO von Little World!

Entschuldige, dass du warten musstest. Wir überarbeiten gerade einige Dinge an unserer Plattform und unserem Matching-Verfahren. Ich bin dein neuer Support-Nutzer und werde dir bei allen Fragen und Problemen helfen.

Da du dich schon vor einiger Zeit registriert hast, wollte ich dich fragen, ob du noch aktiv auf der Suche bist? Antworte mir gerne mit einer schnellen Nachricht oder drücke kurz auf diesen Knopf: <a href="/user/still_active/">Ich suche noch ein Match!</a>

Solange du auf dein Match wartest, kannst du dir schon mal den <a href="https://home.little-world.com/leitfaden">Gesprächsleitfaden</a> anschauen. Hier findest du viele hilfreiche Tipps und Antworten auf mögliche Fragen.

Viele Grüße aus Aachen 👋🏼
"""

make_tim_mangement_admin = {
  "title": "Set Tim As Management User For User",
  "description": "Replace that users current management user with Tim.",
  "type": "object",
  "required": [
    "user_id"
  ],
  "properties": {
    "user_id": {
        "type": "integer",
        "description": "The user id of the user to set Tim as management user for."
    },
    "old_management_mail": {
        "type": "string",
        "description": "The old management users email",
        "default": "littleworld.management@gmail.com"
    },
    "send_management_changed_message": {
        "type": "boolean",
        "default": True
    },
    "custom_message": {
        "type": "boolean",
        "default": False,
    },
    "message": {
        "type": "string",
        "description": "The message to send to the user. Only used if send_management_changed_message is true.",
        "default": default_tim_management_changed_message
    }
  }
}

delete_user_censor_profile = {
    "title": "Delete User Censor Profile", 
    "description": "Delete the user and censor their profile.",
    "type": "object",
    "required": [
        "user_id"
    ],
    "properties": {
        "user_id": {
            "type": "integer",
            "description": "The user id of the user to delete."
        },
        "send_deletion_email": {
            "type": "boolean",
            "default": False
        }
    }
}

_send_sms_to_user = {
    "title": "Send SMS To User",
    "description": "Send an SMS to a user or a number.",
    "type": "object",
    "required": [
        "user_id",
        "message"
    ],
    "properties": {
        "user_id": {
            "type": "integer",
            "description": "The user id of the user to send the sms to."
        },
        "message": {
            "type": "string",
            "description": "The message to send to the user."
        }
    }
}

_send_sms_to_number = {
    "title": "Send SMS To Number",
    "description": "Send an SMS to a number.",
    "type": "object",
    "required": [
        "number",
        "message"
    ],
    "properties": {
        "number": {
            "type": "string",
            "description": "The number to send the sms to."
        },
        "message": {
            "type": "string",
            "description": "The message to send to the user."
        }
    }
}

change_user_matching_state = {
    "title": "Change User Matching State",
    "description": "Change the matching state of a user.",
    "type": "object",
    "required": [
        "user_id",
        "searching"
    ],
    "properties": {
        "user_id": {
            "type": "integer",
            "description": "The user id of the user to change the matching state for."
        },
        "searching": {
            "type": "boolean",
            "description": "The new matching state of the user."
        }
    }
}

flag_user_test_spam_legit = {
    "title": "Flag User As Test Spam Legit",
    "description": "Flag a user as test spam legit.",
    "type": "object",
    "required": [
        "user_id",
        "spam_test_legit"
    ],
    "properties": {
        "user_id": {
            "type": "integer",
            "description": "The user id of the user to flag."
        },
        "spam_test_legit": {
            "type": "string",
            "choices": ["spam", "legit", "test"],
            "description": "The new spam legit state of the user."
        }
    }
}


def check_management_access_right(request, user):
    from management.models import State
    if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
        return Response({
            "msg": "You are not allowed to access this user!"
        }, status=401)
        
    # Now we can check if 'obj'-user is in request.user.state.managed_users ( only if not staff )
    if not request.user.is_staff and not request.user.state.managed_users.filter(pk=user.pk).exists():
        return Response({
            "msg": "You are not allowed to access this user!"
        }, status=401)
    
    return True



def perform_user_deletion(user, management_user=None, send_deletion_email=False):
    from management.models import State, Profile
    from emails import mails
    
    if send_deletion_email:
        user.send_email(
           subject="Dein Account wurde gelöscht", 
           mail_data=mails.get_mail_data_by_name("account_deleted"),
           mail_params=mails.AccountDeletedEmailParams(
            first_name=user.profile.first_name,
           )
        )

    user.is_active = False
    user.email = f"deleted_{user.email}"
    user.first_name = "deleted"
    user.set_unusable_password()
    user.save()
    
    from management.models import MangementTask
    task = MangementTask.create_task(
        user=user,
        description="Cleanup user delete data",
        management_user=management_user
    )
    user.state.management_tasks.add(task)
    user.state.save()
    
    
    user.profile.first_name = f"deleted, {user.profile.first_name}"
    user.profile.second_name = f"deleted, {user.profile.second_name}"
    user.profile.image_type = Profile.ImageTypeChoice.AVATAR
    user.profile.avatar_config = {}
    user.profile.phone_mobile = f"deleted, {user.profile.phone_mobile}"
    user.profile.save()
    
@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def flag_user_spam_test_legit(request):

    from management.models import State, Profile
    from management.controller import get_user_by_pk, make_tim_support_user
    
    user = get_user_by_pk(request.data["user_id"])

    access = check_management_access_right(request, user)
    if access != True:
        return access
    
    us = request.user.state
    
    if request.data["spam_test_legit"] == "spam":
        us.user_category = State.UserCategoryChoices.SPAM
    elif request.data["spam_test_legit"] == "test":
        us.user_category = State.UserCategoryChoices.TEST
    elif request.data["spam_test_legit"] == "legit":
        us.user_category = State.UserCategoryChoices.LEGIT
    us.save()
    return Response({"success": True})


@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def change_user_matching_state(request):

    from management.models import State, Profile
    from management.controller import get_user_by_pk, make_tim_support_user
    
    user = get_user_by_pk(request.data["user_id"])

    access = check_management_access_right(request, user)
    if access != True:
        return access
    
    assert not (user.is_staff or user.is_superuser), "You can't delete a staff or superuser!"
    assert not user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER), "You can't delete a matching user!"
    user.state.matching_state = State.MatchingStateChoices.SEARCHING if request.data["searching"] else State.MatchingStateChoices.NOT_SEARCHING
    user.state.save()
    return Response({"success": True})

@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def delete_user(request):
    """
    Sets a user to in-active and overwrites all the personal infor for that user
    This assures the user data can still be recovered with some effort but the user cannot:
    - login anymore
    """
    from management.models import State, Profile
    from management.controller import get_user_by_pk, make_tim_support_user
    
    user = get_user_by_pk(request.data["user_id"])

    access = check_management_access_right(request, user)
    if access != True:
        return access
    
    assert not (user.is_staff or user.is_superuser), "You can't delete a staff or superuser!"
    assert not user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER), "You can't delete a matching user!"
    
    perform_user_deletion(user, management_user=request.user, send_deletion_email=request.data.get("send_deletion_email", False))
    
    return Response({"success": True})


@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def send_sms_to_number(request):
    # TODO: Shouldn't be accessible for matching users
    from django.conf import settings

    client = _get_client() 
    response = client.messages.create(
        body=request.data["message"],
        from_=settings.TWILIO_SMS_NUMBER,
        to=request.data["number"]
    )
    
    return Response({"success": True})
    
@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def send_sms_to_user(request):
    from management.models import State
    from management.controller import get_user_by_pk, make_tim_support_user
    
    user = get_user_by_pk(request.data["user_id"])
    
    access = check_management_access_right(request, user)
    if access != True:
        return access
    
    from management.models import SmsModel, SmsSerializer

    sms_obj = SmsModel.send_sms(
        recipient=user, 
        send_initator=request.user, 
        message=request.data["message"]
    )
    
    from django.conf import settings

    client = _get_client() 
    response = client.messages.create(
        body=request.data["message"],
        from_=settings.TWILIO_SMS_NUMBER,
        to=user.profile.phone_mobile
    )
    
    sms_obj.twilio_response = response.__dict__
    sms_obj.save()
    
    return Response(SmsSerializer(sms_obj).data)

@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def make_tim_mangement_admin_action(request):
    from management.models import State
    from management.controller import get_user_by_pk, make_tim_support_user

    user = get_user_by_pk(request.data["user_id"])
    
    access = check_management_access_right(request, user)
    if access != True:
        return access

    make_tim_support_user(
        user, 
        old_management_mail=request.data.get("old_management_mail", "littleworld.management@gmail.com"),
        send_message=request.data.get("send_management_changed_message", True), 
        custom_message=request.data.get("message", None) if request.data.get("custom_message", False) else None)
    return Response({"success": True})

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def admin_panel_v2_actions(request):

    return Response({
        "make_tim_mangement_admin": {
            "route": "/api/admin/quick_actions/make_tim_mangement_admin/",
            "schema": make_tim_mangement_admin,
            "ui_schema": {
                "message": {
                    "ui:widget": "textarea"
                }
            }
        },
        "delete_user": {
            "route": "/api/admin/quick_actions/delete_user/",    
            "schema": delete_user_censor_profile,
            "ui_schema": {}
        },
        "send_sms_to_user": {
            "route": "/api/admin/quick_actions/send_sms_to_user/",
            "schema": _send_sms_to_user,
            "ui_schema": {}
        }
    })

action_routes = [
    path(_api_url('quick_actions', admin=True), admin_panel_v2_actions),
    path(_api_url('quick_actions/make_tim_mangement_admin', admin=True), make_tim_mangement_admin_action),
    path(_api_url('quick_actions/delete_user', admin=True), delete_user),
    path(_api_url('quick_actions/send_sms_to_user', admin=True), send_sms_to_user),
    path(_api_url('quick_actions/change_user_matching_state', admin=True), change_user_matching_state),
]
