from django.urls import path, include, re_path
from .consumers import messages
from . import api

messages_api_user_list = api.messages.MessagesModelViewSet.as_view({
    'get': 'list',
})

message_api_user = api.messages.MessagesModelViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
})

messages_api_user_send = api.messages.MessagesModelViewSet.as_view({
    'post': 'send',
})

messages_api_user_read = api.messages.MessagesModelViewSet.as_view({
    'post': 'read',
})

chat_api_user_list = api.chats.ChatsModelViewSet.as_view({
    'get': 'list',
})


chat_api_user = api.chats.ChatsModelViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
})


urlpatterns = [
    path("api/chats/", chat_api_user_list),
    path("api/chats/<str:pk>/", chat_api_user),
    path("api/callbacks/", messages.get_all_websocket_callback_messsages),
    path("api/callbacks/send/<str:callback_name>/<str:user_id>/", messages.send_test_callback),
    path("api/messages/", messages_api_user_list),
    path("api/messages/<str:chat_uuid>/send/", messages_api_user_send),
    path("api/messages/<str:chat_uuid>/", messages_api_user_list),
    path("api/messages/<str:pk>/read/", messages_api_user_send),
    path("api/messages/<str:pk>/", message_api_user),
]
