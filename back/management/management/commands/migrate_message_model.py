
from django.core.management.base import BaseCommand
import json
from bs4 import BeautifulSoup
from chat_old.django_private_chat2.models import DialogsModel, MessageModel
from chat.models import Chat, Message

def transfor_old_to_new_messageformat(message_text):
    soup = BeautifulSoup(message_text, "html.parser")
    all_tags = [tag for tag in soup.find_all()]
    
    placeholders = {}

    def convert_old_tag_to_datatag(old_tag):
        attributes = old_tag.attrs
        print("ARGS", json.dumps(attributes))
        
        new_tag = f'<{old_tag.name} {json.dumps(attributes)}></{old_tag.name}>'
        placeholder = f"||||{len(placeholders)}||||"
        return new_tag, placeholder

    for tag in all_tags:
        new_tag, placeholder = convert_old_tag_to_datatag(tag)
        placeholders[placeholder] = new_tag
        tag.replaceWith(placeholder)
        
    for placeholder, tag in placeholders.items():
        new_message = new_message.replace(placeholder, tag)

    return new_message

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Transforms all:
        # - DialogsModel -> Chat
        # - MessageModel -> Message
        
        messages_old = MessageModel.objects.all()
        dialogs_old = DialogsModel.objects.all()
        
        counts = {
            "dialogs": dialogs_old.count(),
            "messages": messages_old.count()
        }
        
        print(f"Found {counts['dialogs']} dialogs & {counts['messages']} of the old models that require migrations")
        
        # 1 - reset all new chats and messages
        existing_chats = Chat.objects.all()
        existing_messages = Message.objects.all()

        print(f"Found {existing_chats.count()} chats with {existing_messages.count()} of the new Model, DELETING them")
        existing_chats.delete()
        existing_messages.delete()
        
        print("Migrating Chats")
        
        c = 0
        for dialog in dialogs_old:
            chat = Chat.objects.create(
                u1=dialog.user1,
                u2=dialog.user2
            )
            c += 1
            print(f"Created chat {c}/{counts['dialogs']}")
        print(f"Created {c} chats, continuing with messages")
        
        # some id's messages are considered to format migration
        from django.db.models import Q
        from management.models.user import User
        from management.models.state import State

        matching_users = User.objects.filter(
            Q(is_staff=True) | 
            Q(state__extra_user_permissions__contains=State.ExtraUserPermissionChoices.MATCHING_USER)
        ).values_list('id', flat=True)
        print(f"Found {matching_users.count()} matching users who's messages will be specificly transformed")
        
        c = 0
        for message in messages_old:
            message_text = message.message
            chat = Chat.get_chat([message.sender, message.recipient])

            if str(message.sender.id) in matching_users:
                print("Matching users message found transforming format")
                message_text = transfor_old_to_new_messageformat(message_text)

            Message.objects.create(
                chat=chat,
                sender=message.sender,
                text=message_text,
                recipient_notified=True, # Default 'true' for all messages so body is notified double
                recipient=message.recipient,
                created=message.created,
                read=message.read,
            )
            c += 1
            print(f"Created message {c}/{counts['messages']}")
        print(f"Created {c} messages")
        
        print(f"Messages before {counts['messages']} and after {Message.objects.all().count()}")
        print(f"Dialogs before {counts['dialogs']} and after {Chat.objects.all().count()}")
        
        print(f"Y = Yes, N = No, Delete all old messages and dialogs?, type 'Y' and press enter.")
        
        user_input = input()

        if user_input == "Y":
            print("Sorry this option is fully disabled in this deployment")
            #messages_old.delete()
            #dialogs_old.delete()
            #print(f"Deleting All old messages")
        else:
            print(f"Did not delete old messages")
        
