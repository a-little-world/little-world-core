from rest_framework.views import APIView
from rest_framework import serializers, status
from drf_spectacular.utils import extend_schema
from rest_framework import authentication, permissions
from django.utils.translation import pgettext_lazy
from dataclasses import dataclass
from rest_framework.response import Response
from ..twilio_handler import get_usr_auth_token
from ..models.rooms import get_rooms_user, Room
from ..controller import get_user_by_hash, send_websocket_callback


@dataclass
class AuthCallRoomApiParams:
    usr_hash: str
    partner_hash: str


class AuthCallRoomApiSerializer(serializers.Serializer):
    usr_hash = serializers.CharField(max_length=255, required=True)
    partner_hash = serializers.CharField(max_length=255, required=True)

    def create(self, validated_data):
        return AuthCallRoomApiParams(**validated_data)


class AuthenticateCallRoom(APIView):
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=AuthCallRoomApiSerializer(many=False))
    def post(self, request):
        """
        Users should call this if they wan't to get an twilio access token to enter a video room 
        this requeses you to send your own and partner user hash
        You can only authenticate a room if you have an activated call room with a person
        call rooms are stored in models.rooms.Room
        """
        serializer = AuthCallRoomApiSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        usr_self = get_user_by_hash(params.usr_hash)
        usr_other = get_user_by_hash(params.partner_hash)

        rooms_with_match = get_rooms_user(usr_self)
        assert rooms_with_match.count(
        ) == 1, f"{usr_self} and {usr_other} have multiple rooms together"
        room = rooms_with_match.first()

        assert isinstance(room, Room)
        if not room.is_active():
            return Response(pgettext_lazy("api.twilio-room-inactive-err",
                                          "Room is marked as inactive, cant authenticate!"),
                            status=status.HTTP_400_BAD_REQUEST)

        usr_auth_token = None
        try:
            usr_auth_token = get_usr_auth_token(room.name, params.usr_hash)
        except Exception as e:
            print(repr(e))  # TODO: this should inline track an exception

        if usr_auth_token:
            return Response({"usr_auth_token": usr_auth_token})
        else:
            return Response(pgettext_lazy("api.twilio-room-auth-failure",
                                          "Room authentication failed!"),
                            status=status.HTTP_400_BAD_REQUEST)


class TwilioCallbackApiSerializer(serializers.Serializer):
    StatusCallbackEvent = serializers.CharField(max_length=255, required=False)
    RoomName = serializers.CharField(max_length=255, required=False)
    ParticipantIdentity = serializers.CharField(max_length=255, required=False)

    def create(self, validated_data):
        return validated_data


class TwilioCallbackApi(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(request=TwilioCallbackApiSerializer(many=False))
    def post(self, request):
        """
        This is the api twilio sends callbacks to 
        """
        serializer = TwilioCallbackApiSerializer(data=request.data)
        serializer.is_valid()  # TODO are extra params ok for django rest serializer?

        params = serializer.save()

        StatusCallbackEvent = params['StatusCallbackEvent']
        RoomName = params['RoomName']
        ParticipantIdentity = params['ParticipantIdentity']

        def get_room_caller_and_participant():
            room = Room.get_room_by_hash(RoomName)
            room_usrs = [room.usr1, room.usr2]
            assert len(
                room_usrs) == 2, "There should never be more than two users per room!"
            usr = get_user_by_hash(ParticipantIdentity)
            assert usr in room_usrs, "User is not in this room! He should try to authenticate it!"
            other_user = [u for u in room_usrs if u != usr][0]
            return room, usr, other_user

        if StatusCallbackEvent == 'participant-disconnected':
            room, caller, participant = get_room_caller_and_participant()

            send_websocket_callback(
                participant,
                f"exited_call:{caller.hash}"
            )
            return Response()
        elif StatusCallbackEvent == 'participant-connected':
            room, caller, participant = get_room_caller_and_participant()

            send_websocket_callback(
                participant,
                f"entered_call:{caller.hash}"
            )
            return Response()
        # Means we havenet handled this callback yet!
        return Response(status=400)
