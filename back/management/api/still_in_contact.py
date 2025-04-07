from rest_framework.decorators import api_view, permission_classes
from management.views.main_frontend import info_card
from django.urls import path

@api_view(["GET"])
@permission_classes([])
def still_in_contact__yes(request):
    user_hash = request.query_params.get("u", None)

    return info_card(
        request,
        title="Thank you for your feedback!",
        content="You've selected that you are still in contact. Please give us some feedback on your match.",
        linkText="Back to app",
        linkTo="/login",
    )

@api_view(["GET"])
@permission_classes([])
def still_in_contact__no(request):
    user_hash = request.query_params.get("u", None)

    return info_card(
        request,
        title="Not in contact anymore?",
        content="You've selected that you are not in contact anymore. If you want a new match, please contact us.",
        linkText="Back to app",
        linkTo="/login",
    )

api_urls = [
    path("still_in_contact/yes", still_in_contact__yes),
    path("still_in_contact/no", still_in_contact__no),
]
