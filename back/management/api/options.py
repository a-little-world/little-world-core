from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from back.utils import transform_add_options_serializer
from management.controller import get_base_management_user
from management.models.profile import SelfProfileSerializer


def get_options_dict():
    bmu = get_base_management_user()

    ProfileWOptions = transform_add_options_serializer(SelfProfileSerializer)
    profile_data = ProfileWOptions(bmu.profile).data
    profile_options = profile_data["options"]
    return {
        "profile": profile_options,
    }


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def get_options(request):
    """
    Get all notifications for the current user
    """
    """
    A helper tag that returns the api trasnlations  
    This can be used by frontends to dynamicly change error translation lanugages without resending requrests
    """

    return Response(get_options_dict())
