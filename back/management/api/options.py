from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from back.utils import transform_add_options_serializer
from management.controller import get_base_management_user
from management.models.profile import SelfProfileSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication


def get_options_dict():
    bmu = get_base_management_user()

    ProfileWOptions = transform_add_options_serializer(SelfProfileSerializer)
    profile_data = ProfileWOptions(bmu.profile).data
    profile_options = profile_data["options"]
    return {
        "profile": profile_options,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def api_options(request):
    """
    Returns API options including form options.
    """
    try:
        return Response(get_options_dict())
    except Exception as e:
        return Response({"error": str(e)}, status=400)
