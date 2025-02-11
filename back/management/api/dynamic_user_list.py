from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.viewsets import ModelViewSet

from management.helpers import IsAdminOrMatchingUser
from management.models.dynamic_user_list import DynamicUserList
from management.models.user import User


class UserSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email"]


class DynamicUserListSerializer(ModelSerializer):
    class Meta:
        model = DynamicUserList
        fields = ["id", "name", "users", "description", "created_at", "updated_at"]


class DynamicUserListGeneralViewSet(ModelViewSet):
    queryset = DynamicUserList.objects.all()
    serializer_class = DynamicUserListSerializer

    def get_permissions(self):
        self.permission_classes = [IsAdminOrMatchingUser]
        return super().get_permissions()


class DynamicUserListSingleViewSet(ModelViewSet):
    queryset = DynamicUserList.objects.all()

    def get_permissions(self):
        self.permission_classes = [IsAdminOrMatchingUser]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == "list" or self.action == "retrieve":
            return UserSerializer
        return DynamicUserListSerializer

    def update(self, request, *args, **kwargs):
        list_id = self.kwargs.get("pk")

        user_ids = request.data["users"]

        users = User.objects.filter(pk__in=user_ids)
        if len(users) != len(user_ids):
            return Response({"error": "Some users do not exist"}, status=status.HTTP_400_BAD_REQUEST)

        userlist = DynamicUserList.objects.filter(id=list_id)

        if userlist is None or len(userlist) > 1:
            return Response(
                {"error": "No Userlist found or more then one for this name"}, status=status.HTTP_404_NOT_FOUND
            )

        userlist[0].name = request.data["name"]
        userlist[0].description = request.data["description"]

        for user_id in user_ids:
            userlist[0].users.add(user_id)

        userlist[0].save()

        serializer = self.get_serializer(userlist, many=True)

        return Response(data=serializer.data, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        list_id = self.kwargs.get("pk")
        try:
            message_list = DynamicUserList.objects.get(id=list_id)
            users = message_list.users.all()
            serializer = self.get_serializer(users, many=True)
            return Response(serializer.data)
        except DynamicUserList.DoesNotExist:
            return Response({"error": "Dynamic user list not found"}, status=status.HTTP_404_NOT_FOUND)


class DynamicUserListSingleUserViewSet(ModelViewSet):
    def get_serializer_class(self):
        return DynamicUserListSerializer

    def destroy(self, request, *args, **kwargs):
        list_id = self.kwargs.get("list_id")
        user_id = self.kwargs.get("user_id")

        if list_id is None or user_id is None:
            return Response({"error": "Please provide a user_id and list_id,"}, status=status.HTTP_400_BAD_REQUEST)

        message_list = DynamicUserList.objects.get(id=list_id)
        if message_list is None:
            return Response({"error": "DynamicUserList for given list_id not found"}, status=status.HTTP_404_NOT_FOUND)

        if message_list.users.remove(user_id) is None:
            serializer = self.get_serializer([message_list], many=True)

            return Response(data=serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": "could not remove the user from the messagelist."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
