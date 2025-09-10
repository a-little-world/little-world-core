from django.db.models import Max, Q, Exists, OuterRef, F
from drf_spectacular.utils import extend_schema, inline_serializer
from management.helpers import DetailedPaginationMixin
from management.models.profile import ProfileSerializer
from management.models.matches import Match
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from management.models.state import State
import datetime

from chat.models import Chat, ChatSerializer, MessageSerializer, Message


def chat_res_seralizer(many=True):
    return inline_serializer(
        name="ChatResult",
        fields={
            "uuid": serializers.UUIDField(),
            "created": serializers.DateTimeField(),
            "newest_message": MessageSerializer(many=False),
            "partner": ProfileSerializer(many=False),
        },
        many=many,
    )


class ChatsModelViewSet(viewsets.ModelViewSet):
    """
    Simple Viewset for modifying user profiles
    """

    allow_user_list = True
    user_editable = []  # For users all fields are ready only on this one!
    serializer_class = ChatSerializer
    permission_classes = [IsAuthenticated]
    queryset = Chat.objects.all()

    pagination_class = DetailedPaginationMixin

    @extend_schema(
        responses={200: chat_res_seralizer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        is_matching_user = self.request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)

        queryset = Chat.objects.filter(Q(u1=self.request.user) | Q(u2=self.request.user)).annotate(
            has_messages=Exists(
                Message.objects.filter(chat_id=OuterRef('pk'))
            ),
            is_active_match=Exists(
                Match.objects.filter(
                    Q(user1=OuterRef('u1'), user2=OuterRef('u2')) |
                    Q(user1=OuterRef('u2'), user2=OuterRef('u1')),
                    active=True
                )
            ),
        ).filter(
            Q(has_messages=True) | Q(is_active_match=True)
        )        

        if is_matching_user:
            queryset = queryset.annotate(
                newest_message_time=Max("message__created"),
                has_messages=Exists(
                    Message.objects.filter(chat_id=OuterRef('pk'))
                )
            ).order_by("-has_messages", "-newest_message_time", "-created")
        else:
            queryset = queryset.annotate(
                newest_message_time=Max("message__created")
            ).order_by("-newest_message_time")
        
        return queryset

    @extend_schema(responses={200: chat_res_seralizer(many=False)})
    @action(detail=False, methods=["post"])
    def get_by_uuid(self, request, chat_uuid=None):
        if not chat_uuid:
            return Response({"error": "chat_uuid is required"}, status=400)

        chat = self.get_queryset().filter(uuid=chat_uuid)
        if not chat.exists():
            return Response({"error": "Chat doesn't exist or you have no permission to interact with it!"}, status=403)

        chat = chat.first()
        return Response(
            self.serializer_class(
                chat,
                context={
                    "request": request,
                },
            ).data
        )
