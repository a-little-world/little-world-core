from django.urls import path
from . import api

messages_api_user_list = api.messages.MessagesModelViewSet.as_view(
    {
        "get": "list",
    }
)

message_api_user = api.messages.MessagesModelViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
    }
)

messages_api_user_send = api.messages.MessagesModelViewSet.as_view(
    {
        "post": "send",
    }
)

messages_api_user_read = api.messages.MessagesModelViewSet.as_view(
    {
        "post": "read",
    }
)

chat_messages_api_user_read = api.messages.MessagesModelViewSet.as_view(
    {
        "post": "chat_read",
    }
)

chat_api_user_list = api.chats.ChatsModelViewSet.as_view(
    {
        "get": "list",
    }
)


chat_api_user = api.chats.ChatsModelViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
    }
)

chat_api_user_get2 = api.chats.ChatsModelViewSet.as_view(
    {
        "get": "get_by_uuid",
    }
)


urlpatterns = [
    path("api/chats/", chat_api_user_list),
    path("api/chats/<str:chat_uuid>/", chat_api_user_get2),
    # path("api/callbacks/", messages.get_all_websocket_callback_messsages),
    # path("api/callbacks/send/<str:callback_name>/<str:user_id>/", messages.send_test_callback),
    path("api/messages/", messages_api_user_list),
    path("api/messages/<str:chat_uuid>/chat_read/", chat_messages_api_user_read),
    path("api/messages/<str:chat_uuid>/send/", messages_api_user_send),
    path("api/messages/<str:chat_uuid>/", messages_api_user_list),
    path("api/messages/<str:pk>/read/", messages_api_user_send),
    path("api/messages/<str:pk>/", message_api_user),
]
