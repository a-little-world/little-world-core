from .admin_panel_v2 import IsAdminOrMatchingUser
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

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
        "default": """
Hallo {first_name}, ich bin Tim, Mitbegründer und CTO von Little World!

Entschuldige, dass du warten musstest. Wir überarbeiten gerade einige Dinge an unserer Plattform und unserem Matching-Verfahren. Ich bin dein neuer Support-Nutzer und werde dir bei allen Fragen und Problemen helfen.

Da du dich schon vor einiger Zeit registriert hast, wollte ich dich fragen, ob du noch aktiv auf der Suche bist? Antworte mir gerne mit einer schnellen Nachricht oder drücke kurz auf diesen Knopf: <a href="/user/still_active/">Ich suche noch ein Match!</a>

Solange du auf dein Match wartest, kannst du dir schon mal den <a href="https://home.little-world.com/leitfaden">Gesprächsleitfaden</a> anschauen. Hier findest du viele hilfreiche Tipps und Antworten auf mögliche Fragen.

Viele Grüße aus Aachen 👋🏼
"""
    }
  }
}

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def admin_panel_v2_actions(request):

    return Response({
        "make_tim_mangement_admin": {
            "route": "",
            "schema": make_tim_mangement_admin,
        }
    })
