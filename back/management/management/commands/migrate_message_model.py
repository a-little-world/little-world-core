
from django.core.management.base import BaseCommand
import csv , sys
import json
from chat_old.django_private_chat2.models import DialogsModel, MessageModel
from chat.models import Chat, Message

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
        
        c = 0
        for message in messages_old:
            chat = Chat.get_chat([message.sender, message.recipient])
            Message.objects.create(
                chat=chat,
                sender=message.sender,
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
            messages_old.delete()
            dialogs_old.delete()
            print(f"Deleting All old messages")
        else:
            print(f"Did not delete old messages")
        
