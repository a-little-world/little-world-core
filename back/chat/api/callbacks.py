from management.models.user import User
from chat.models import Message
from management.models.consumer_connections import ConsumerConnections
from enum import Enum

def build_payload(action: str, payload: dict):
    return {
        "action": action,
        "payload": payload
    }
    
def send_callback(user: User, action: str, payload: dict):
    ConsumerConnections.async_notify_connections(
        user, 
        event="reduction",
        payload=build_payload(
            action,
            payload
        )
    )

class Actions(Enum):
    MESSAGE_INCOMING = "MESSAGE_INCOMING"
    OUTGOING_MESSAGE_SEND = "OUTGOING_MESSAGE_SEND"

def message_incoming(user: User, serialized_message):
    """
    A message was just send by another user
    """
    send_callback(user, Actions.MESSAGE_INCOMING.value, serialized_message)
    
def message_send(user: User, serialized_message):
    """
    When a user sends a message & that message was saved to db 
    """
    send_callback(user, Actions.OUTGOING_MESSAGE_SEND.value, serialized_message)