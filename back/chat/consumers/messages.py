from enum import Enum
import json
from typing import Optional
from back.utils import CoolerJson
from dataclasses import dataclass
from channels.layers import get_channel_layer
from asgiref.sync import sync_to_async, async_to_sync
from dataclasses import dataclass, asdict, fields, MISSING
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response


class MessageTypes(Enum):
    no_type = "no_type"
    user_went_online = "user_went_online"
    user_went_offline = "user_went_offline"
    match_proposal_added = "match_proposal_added"
    unconfirmed_match_added = "unconfirmed_match_added" # A new match but hasn't been viewed yet
    block_incoming_call = "block_incoming_call"
    new_active_call = "new_active_call"
    new_message = "new_message"
    messages_read_chat = "messages_read_chat"
    pre_matching_appointment_booked = "pre_matching_appointment_booked"
    
    
    
def send_message(user_id, type: MessageTypes, data):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(user_id, data)

@dataclass
class MessageBase:

    def dict(self):
        return self.__dict__.copy()
    
    def dict_valid(self):
        return json.loads(json.dumps(self.dict(), cls=CoolerJson))
    
    def json(self):
        return json.dumps(self.dict())
    
    def action_dict(self):
        # basicly 'send_message' requires dict that json serializable, 
        # so sadly dumping and parsing is required to assure that
        return json.loads(self.action_json())
    
    def action_json(self):
        assert hasattr(self, "build_redux_action"), "Message must have a build_redux_action method"
        return json.dumps(self.build_redux_action(), cls=CoolerJson)
    
    def send(self, user_id):
        send_message(user_id, self.type, self.dict_valid())
    
@dataclass
class OutUserWentOnline(MessageBase):
    sender_id: str
    type: str = MessageTypes.user_went_online.value
    
    def build_redux_action(self):
        return {
            "action": "updateMatchProfile", 
            "payload": {
                "partnerId": self.sender_id,
                "profile": {
                    "isOnline": True
                }
            }
        }
    
@dataclass
class OutUserWentOffline(MessageBase):
    sender_id: str
    type: str = MessageTypes.user_went_offline.value
    
    def build_redux_action(self):
        return {
            "action": "updateMatchProfile", 
            "payload": {
                "partnerId": self.sender_id,
                "profile": {
                    "isOnline": False
                }
            }
        }
        
@dataclass 
class InMatchProposalAdded(MessageBase):
    match: dict
    category: str = "proposed"
    type: str = MessageTypes.match_proposal_added.value
    
    def build_redux_action(self):
        return {
            "action": "addMatch", 
            "payload": {
                "category": self.category,
                "match": self.match
            }
        }
        
@dataclass
class InUnconfirmedMatchAdded(MessageBase):
    match: dict
    category: str = "unconfirmed"
    type: str = MessageTypes.unconfirmed_match_added.value
    
    def build_redux_action(self):
        return {
            "action": "addMatch", 
            "payload": {
                "category": self.category,
                "match": self.match
            }
        }
        
@dataclass
class InBlockIncomingCall(MessageBase):
    sender_id: str
    type: str = MessageTypes.block_incoming_call.value
    
    def build_redux_action(self):
        return {
            "action": "blockIncomingCall", 
            "payload": {
                "userId": self.sender_id
            }
        }
        
@dataclass
class NewActiveCallRoom(MessageBase):
    call_room: dict
    type: str = MessageTypes.new_active_call.value
    
    def build_redux_action(self):
        return {
            "action": "addActiveCallRoom", 
            "payload": self.call_room
        }
        
@dataclass
class PreMatchingAppointmentBooked(MessageBase):
    appointment: dict
    type: str = MessageTypes.pre_matching_appointment_booked.value
    
    def build_redux_action(self):
        return {
            "action": "preMatchingAppointmentBooked", 
            "payload": self.appointment
        }
        
@dataclass
class MessagesReadChat(MessageBase):
    chat_id: str
    user_id: str
    type: str = MessageTypes.messages_read_chat.value
    
    def build_redux_action(self):
        return {
            "action": "markChatMessagesRead", 
            "payload": {
                "chatId": self.chat_id,
                "userId": self.user_id
            }
        }
        
@dataclass
class NewMessage(MessageBase):
    message: dict
    chat_id: str
    meta_chat_obj: Optional[dict] = None # holds additional 'chatObject' such that the frontend can hidrate it if it's not present
    type: str = MessageTypes.new_message.value
    
    def build_redux_action(self):
        return {
            "action": "addMessage", 
            "payload": {
                "message": self.message,
                "chatId": self.chat_id,
                "metaChatObj": self.meta_chat_obj
            }
        }

CALLBACKS = {
    MessageTypes.user_went_online.value: OutUserWentOnline,
    MessageTypes.user_went_offline.value: OutUserWentOffline,
    MessageTypes.match_proposal_added.value: InMatchProposalAdded,
    MessageTypes.unconfirmed_match_added.value: InUnconfirmedMatchAdded,
    MessageTypes.block_incoming_call.value: InBlockIncomingCall,
    MessageTypes.new_active_call.value: NewActiveCallRoom,
    MessageTypes.pre_matching_appointment_booked.value: PreMatchingAppointmentBooked,
    MessageTypes.new_message.value: NewMessage,
    MessageTypes.messages_read_chat.value: MessagesReadChat
}
        
# @api_view(['POST'])
# @permission_classes([IsAdminOrMatchingUser])
# def send_test_callback(request, callback_name, user_id):
#    params = request.data
#    callback = CALLBACKS[callback_name]
#    callback(**params).send(user_id)
#    from management.controller import get_user_by_hash
#    try:
#        get_user_by_hash(user_id)
#    except:
#        return Response({"status": "error", "message": "User not found"}, status=404)
#    return Response({"status": "ok"})
    
#@api_view(['GET'])
#@permission_classes([IsAdminOrMatchingUser])
#def get_all_websocket_callback_messsages(request):
#    
#    def extract_annotations(class_obj):
#        annotations = {field.name: {
#            "type" : field.type.__name__,
#            "default": field.default if field.default != MISSING else None,
#        } for field in fields(class_obj)}
#        return annotations
#    
#    
#    annotations = {key: extract_annotations(CALLBACKS[key]) for key, callback in CALLBACKS.items()}
#
#    list_annotations = []
#    for key in annotations:
#        list_annotations.append({
#            "type": key,
#            "fields": annotations[key]
#        })
#    return Response(list_annotations)