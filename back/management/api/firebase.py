from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from django.urls import path
from django.conf import settings


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def firebase_config(request):
    """
    Returns Firebase configuration for the client.
    """
    try:
        return Response({
            "firebaseClientConfig": settings.FIREBASE_CLIENT_CONFIG,
            "firebasePublicVapidKey": settings.FIREBASE_PUBLIC_VAPID_KEY,
        })
    except Exception as e:
        return Response({"error": str(e)}, status=400)


api_urls = [
    path("api/firebase", firebase_config, name="firebase_config_api"),
] 