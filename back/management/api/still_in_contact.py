from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import redirect
from management.views.main_frontend import info_card
from management.models.matches import Match
from django.utils import timezone
from management.models.user import User

def get_redirect_url(redirect_slug: str, user_hash: str, match_uuid: str) -> (bool, str):
    if redirect_slug == "info-screen":
        return False, "info-screen"
    elif redirect_slug == "match-form1":
        return True, f"https://docs.google.com/forms/d/e/1FAIpQLScZpHVBkd9oXMTXGwH6aIUS8-Ep3LGbmHzx0wKYTA0fDpzJtQ/viewform?entry.1868418501={user_hash}&entry.1064841735={match_uuid}"
    else:
        return False, "info-screen"

@api_view(["GET"])
@permission_classes([])
def still_in_contact(request, match_uuid: str, answer: str):
    # ? user_hash ? user_token ?
    user_hash = request.query_params.get("user_hash", None)
    user_token = request.query_params.get("user_token", None)
    redirect_slug = request.query_params.get("redirect_slug", "info-screen")
    
    user = User.objects.get(hash=user_hash)
    if not user_token == str(user.state.still_in_contact_form_access_token_user):
        return Response({"error": "Invalid user token"}, status=403)
    
    # 1 - Mark the match as 'completed_off_plattform'
    match = Match.objects.get(uuid=match_uuid)
    match.completed_off_plattform = True
    match.completed_off_plattform_auto_marked_at = timezone.now()
    match.auto_marking_updated_logs.append({
        "time": str(timezone.now()),
        "user_hash": str(user_hash),
        "user_token": str(user_token),
        "redirect_slug": str(redirect_slug),
        "answer": str(answer),
    })
    match.save()

    # 2 - Either re-direct or render a info card
    should_redirect, redirect_url = get_redirect_url(redirect_slug, user_hash, match_uuid)
    if should_redirect:
        return redirect(redirect_url)
    else:
        # TODO: refine what is rendered in this case!
        return info_card(
            request,
            title="Thank you for your feedback!",
            content="You've selected that you are still in contact. Please give us some feedback on your match.",
            linkText="Back to app",
            linkTo="/login",
        )

api_urls = [
    path("api/still_in_contact/<str:match_uuid>/<str:answer>/", still_in_contact),
]
