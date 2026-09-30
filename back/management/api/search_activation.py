from django.core.exceptions import ValidationError
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from translations import get_translation

from management.models.state import State
from management.models.user import User
from management.views.main_frontend import info_card

SUPPORTED_CARD_LANGS = ("de", "en")


def get_card_lang(user) -> str:
    lang = getattr(user.profile, "display_language", None)
    return lang if lang in SUPPORTED_CARD_LANGS else "de"


def render_search_activation_card(request, status_slug: str, lang: str):
    link_to = "/login?next=/app/" if status_slug == "success" else "/app/"
    return info_card(
        request,
        title=get_translation(f"info_card.activate_searching_{status_slug}.title", lang=lang),
        content=get_translation(f"info_card.activate_searching_{status_slug}.content", lang=lang),
        linkText=get_translation(f"info_card.activate_searching_{status_slug}.link_text", lang=lang),
        linkTo=link_to,
    )


@api_view(["GET"])
@permission_classes([])
def activate_searching(request, user_uuid: str, user_token: str):
    """
    Public one-click link that activates the user's searching state.

    Used in outreach emails/chats for inactive volunteers. The link is static per
    user and validated against State.search_activation_token.
    """
    try:
        user = User.objects.get(uuid=user_uuid)
    except (User.DoesNotExist, ValidationError, ValueError):
        return render_search_activation_card(request, "failure", "de")

    if str(user.state.search_activation_token) != str(user_token):
        return Response({"error": "Invalid user token"}, status=403)

    state = user.state
    state.change_searching_state(State.SearchingStateChoices.SEARCHING)
    if state.unresponsive:
        state.unresponsive = False
    state.still_active_reminder_confirmed = True
    state.save()

    return render_search_activation_card(request, "success", get_card_lang(user))


api_urls = [
    path("api/user/activate_searching/<str:user_uuid>/<str:user_token>/", activate_searching),
]
