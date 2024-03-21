from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from video.models import LiveKitRoom
from management.models.user import User
from rest_framework.response import Response
from django.conf import settings
from dataclasses import dataclass
from livekit import api as livekit_api
import asyncio

@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def livekit_webhook(request):
    assert request.query_params["secret"] == settings.LIVEKIT_WEBHOOK_SECRET, "Invalid secret"
    pass

@dataclass
class AuthenticateRoomParams:
    partner_id: str
    
async def create_livekit_room(room_name):
    lkapi = livekit_api.LiveKitAPI(
        settings.LIVEKIT_URL
    )
    results = await lkapi.room.list_rooms(livekit_api.ListRoomsRequest())
    if not room_name in [room.name for room in results.rooms]: 
        room_info = await lkapi.room.create_room(
            livekit_api.CreateRoomRequest(name=room_name),
        )
        print("Created room that didn't exist:", room_name)
    await lkapi.aclose()

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def authenticate_live_kit_room(request):
    
    # 1 - gather the user
    user = request.user
    partner = User.objects.get(hash=request.data["partner_id"])
    
    # 2 - the room MUST exist for the user and the partner ( will error if not )
    livekit_room = LiveKitRoom.get_room(user, partner)
    
    # 3 make sure the livekit room is active
    asyncio.get_event_loop().run_until_complete(create_livekit_room(str(livekit_room.uuid)))
    
    # 4 - generate autenticaton token
    token = livekit_api.AccessToken(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET
    ).with_identity(user.hash) \
        .with_name(f"{user.profile.fist_name} {user.profile.second_name[:1]}") \
        .with_grants(livekit_api.VideoGrants(
            room_join=True,
            room=str(livekit_room.uuid),
        )).to_jwt()

    return Response({"token": str(token)})


