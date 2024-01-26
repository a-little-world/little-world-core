from channels.db import database_sync_to_async
from management.models.user import User
from management.models.state import State
from django.utils import timezone
from chat.models import Chat, ChatConnections, ChatSessions

@database_sync_to_async
def is_staff_or_matching(user):
    return user.is_staff or user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)

@database_sync_to_async
def connect_user(user):
    connection = ChatConnections.objects.filter(user=user)
    if connection.exists():
        connection = connection.first()
        connection.is_online = True
        connection.last_seen = timezone.now()
        connection.save()
    else:
        connection = ChatConnections.objects.create(
            user=user, 
            is_online=True
        )
    return connection

@database_sync_to_async
def disconnect_user(user):
    connection = ChatConnections.objects.filter(user=user)
    if connection.exists():
        connection = connection.first()
        connection.is_online = False
        connection.save()
    # then we also create a new chat session ( a log of the ongoing connection for that user)
    ChatSessions.objects.create(
        user=user, 
        start_time=connection.last_seen,
        end_time=timezone.now()
    )

@database_sync_to_async
def get_all_chat_user_ids(user):
    """
Retruns a list of all raw user_ids that have a chat with that user 
NOTE: also returns the owns user user_id!
    """
    chat_uuids = list(sum(Chat.get_chats(user).values_list('u1__hash', 'u2__hash'), ()))
    return chat_uuids