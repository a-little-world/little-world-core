from rest_framework.serializers import ModelSerializer
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status

from management.models.message_broadcast import MessageBroadcastList
from management.models.user import User
from management.helpers import IsAdminOrMatchingUser


class UserSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email"]


class MessageBroadcastListSerializer(ModelSerializer):
    class Meta:
        model = MessageBroadcastList
        fields = ["id", "name", "users", "description", "created_at", "updated_at"]


class MessageBroadcastListViewSet(ModelViewSet):
    queryset = MessageBroadcastList.objects.all()
    serializer_class = MessageBroadcastListSerializer

    def get_permissions(self):
        self.permission_classes = [IsAdminOrMatchingUser]
        return super().get_permissions()


class MessageBroadcastListViewSetUsers(ModelViewSet):
    queryset = MessageBroadcastList.objects.all()

    def get_permissions(self):
        self.permission_classes = [IsAdminOrMatchingUser]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == "list" or self.action == "retrieve":
            return UserSerializer
        return MessageBroadcastListSerializer

    def list(self, request, *args, **kwargs):
        list_id = self.kwargs.get("pk")
        try:
            message_list = MessageBroadcastList.objects.get(id=list_id)
            users = message_list.users.all()
            serializer = self.get_serializer(users, many=True)
            return Response(serializer.data)
        except MessageBroadcastList.DoesNotExist:
            return Response({"error": "Message broadcast list not found"}, status=status.HTTP_404_NOT_FOUND)
