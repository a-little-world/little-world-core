from django.conf import settings
from django.shortcuts import redirect
from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from translations import get_translation

from management.models.matches import Match
from management.models.user import User
from management.views.main_frontend import info_card


def get_redirect_url(redirect_slug: str, user_uuid: str, match_uuid: str) -> (bool, str):
    if redirect_slug == "info-screen":
        return False, "info-screen"
    elif redirect_slug == "match-form1":
        # used by 'automatic-emails-m032' and 'automatic-emails-m033' and 'automatic-emails-m042'
        return (
            True,
            f"https://docs.google.com/forms/d/e/1FAIpQLScZpHVBkd9oXMTXGwH6aIUS8-Ep3LGbmHzx0wKYTA0fDpzJtQ/viewform?entry.1868418501={user_uuid}&entry.1064841735={match_uuid}",
        )
    else:
        return False, "info-screen"


@api_view(["GET"])
@permission_classes([])
def still_in_contact(request, match_uuid: str, answer: str):
    # ? user_uuid ? user_token ?
    user_uuid = request.query_params.get("user_uuid", None)
    legacy_user_hash = None
    if user_uuid is None:
        # Legacy fallback for links sent before uuid migration.
        # The old 'user_hash' field is a double-UUID CharField, not a UUIDField,
        # so it must be looked up via User.hash rather than User.uuid.
        legacy_user_hash = request.query_params.get("user_hash", None)
    user_token = request.query_params.get("user_token", None)
    redirect_slug = request.query_params.get("redirect_slug", "info-screen")

    if legacy_user_hash is not None:
        user = User.objects.get(hash=legacy_user_hash)
    else:
        user = User.objects.get(uuid=user_uuid)
    if not user_token == str(user.state.still_in_contact_form_access_token_user):
        return Response({"error": "Invalid user token"}, status=403)

    # 1 - Mark the match as 'completed_off_plattform'
    completed_off_plattform = True if answer == "yes" else False
    match = Match.objects.get(uuid=match_uuid)

    if not match.user1 == user and not match.user2 == user:
        return Response({"error": "You are not allowed to mark this match"}, status=403)

    match.completed_off_plattform = completed_off_plattform
    if match.completed_off_plattform_auto_marked_at is None:
        match.completed_off_plattform_auto_marked_at = timezone.now()
    match.auto_marking_updated_logs.append(
        {
            "time": str(timezone.now()),
            "user_uuid": str(user_uuid),
            "user_token": str(user_token),
            "redirect_slug": str(redirect_slug),
            "answer": str(answer),
        }
    )
    match.save()

    # 1.5 Check if auto action should be taken e.g.: after marking yes for a match we should send a confirm email 'automatic-emails-m051'
    if answer == "yes" and redirect_slug == "match-form1" and not match.auto_email_m051_send:
        if settings.ENABLE_AUTO_EMAILS__M051:
            from management.tasks import send_email_background

            emulated_send = bool(settings.DJANGO_TESTING) or bool(settings.EMULATE_AUTO_EMAILS__M051)
            # TODO: confirm if should send to one or both users
            send_email_background.delay(
                "automatic-emails-m051", user_id=user.id, match_id=match.pk, emulated_send=emulated_send
            )
            match.auto_email_m051_send = True
            match.save()

    # 2 - Either re-direct or render a info card
    # TODO: restict to hardcoded or env list to avoid any injection option ( though we have the token so we would know the account that tried shenanigans )
    should_redirect, redirect_url = get_redirect_url(redirect_slug, user_uuid, match_uuid)
    if should_redirect:
        return redirect(redirect_url)
    else:
        return info_card(
            request,
            title=get_translation(f"info_card.still_in_contact_{answer}.title", lang="de"),
            content=get_translation(f"info_card.still_in_contact_{answer}.content", lang="de"),
            linkText=get_translation(f"info_card.still_in_contact_{answer}.link_text", lang="de"),
            linkTo="/login",
        )


api_urls = [
    path("api/still_in_contact/<str:match_uuid>/<str:answer>/", still_in_contact),
]
