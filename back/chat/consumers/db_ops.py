from channels.db import database_sync_to_async
from chat.models import Chat, ChatConnections, ChatSessions
from django.utils import timezone
from management.permissions import ManagementPermission


@database_sync_to_async
def is_staff_or_matching(user):
    return user.is_staff or user.has_perm(ManagementPermission.MATCHING_USER)


@database_sync_to_async
def connect_user(user):
    connection = ChatConnections.objects.filter(user=user)
    if connection.exists():
        existing_connection = connection.first()
        if existing_connection is None:
            connection = ChatConnections.objects.create(user=user, is_online=True)
        else:
            existing_connection.is_online = True
            existing_connection.last_seen = timezone.now()
            existing_connection.save()
            connection = existing_connection
    else:
        connection = ChatConnections.objects.create(user=user, is_online=True)
    return connection


@database_sync_to_async
def disconnect_user(user):
    connection = ChatConnections.objects.filter(user=user)
    last_seen = None
    if connection.exists():
        existing_connection = connection.first()
        if existing_connection is None:
            raise Exception("User was not connected, but still disconnected")
        last_seen = existing_connection.last_seen
        existing_connection.is_online = False
        existing_connection.save()
    else:
        raise Exception("User was not connected, but still disconnected")

    # then we also create a new chat session ( a log of the ongoing connection for that user)
    ChatSessions.objects.create(user=user, start_time=last_seen, end_time=timezone.now())


@database_sync_to_async
def get_all_chat_user_ids(user):
    """
    Retruns a list of all raw user_ids that have a chat with that user
    NOTE: also returns the owns user user_id!
    """
    chat_uuids = set(sum(Chat.get_chats(user).values_list("u1__uuid", "u2__uuid"), ()))
    return {str(user_uuid) for user_uuid in chat_uuids if user_uuid is not None}
