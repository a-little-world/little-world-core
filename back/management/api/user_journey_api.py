from management.user_journey import PerUserBuckets
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from back.utils import _api_url
from django.urls import path, re_path
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from rest_framework_dataclasses.serializers import DataclassSerializer
from rest_framework.permissions import IsAuthenticated
from management.views.admin_panel_v2 import IsAdminOrMatchingUser


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsAdminOrMatchingUser])
def get_user_journey(request):
    user_journey = PerUserBuckets.get_schema()
    return Response(user_journey)



api_routes = [
    path(_api_url('user_journey/schema', admin=True), get_user_journey),
]
