from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from management.views.main_frontend import info_card


@api_view(["GET"])
@permission_classes([])
def landing_page(request):
    return info_card(request, title=settings.LANDINGPAGE_PLACEHOLDER_TITLE, content="here could be a landing page", linkText="Go to the app", linkTo="/login")
