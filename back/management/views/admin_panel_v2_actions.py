from .admin_panel_v2 import IsAdminOrMatchingUser
from back.utils import _api_url
from django.urls import path, re_path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

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

@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def make_tim_mangement_admin_action(request):
    from management.models import State
    from management.controller import get_user_by_pk, make_tim_support_user

    user = get_user_by_pk(request.data["user_id"])

    if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
        return Response({
            "msg": "You are not allowed to access this user!"
        }, status=401)
        
    # Now we can check if 'obj'-user is in request.user.state.managed_users ( only if not staff )
    if not request.user.is_staff and not request.user.state.managed_users.filter(pk=user.pk).exists():
        return Response({
            "msg": "You are not allowed to access this user!"
        }, status=401)
    
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
        }
    })

action_routes = [
    path(_api_url('quick_actions', admin=True), admin_panel_v2_actions),
    path(_api_url('quick_actions/make_tim_mangement_admin', admin=True), make_tim_mangement_admin_action),
]
