import json

from django.db.models import Q
from django.utils import timezone
from management.models.matches import Match
from management.models.user import PushNotificationType, User
from management.tasks import push_notification_background, send_email_background
from video.models import LivekitSession

from chat.models import Chat, ChatSerializer, Message, MessageAttachment, MessageSerializer


class MessageSendValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class MatchSendForbidden(Exception):
    pass


def process_message_attachment(file, caption: str = "") -> tuple[str, MessageAttachment, bool]:
    if file.size > 3 * 1024 * 1024:
        raise MessageSendValidationError("File size too large. Maximum size is 3MB.")

    if not file.name or "." not in file.name:
        raise MessageSendValidationError("Invalid file format. File must have a valid extension.")

    attachment = MessageAttachment.objects.create(file=file)
    if not attachment or not attachment.file:
        raise MessageSendValidationError("Failed to process file attachment.")

    file_extension = file.name.split(".")[-1].lower()
    is_image = file_extension in ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "ico", "webp"]

    escaped_title = json.dumps("Image" if is_image else file.name)
    escaped_caption = json.dumps(caption)
    escaped_attachment_link = json.dumps(attachment.file.url)

    if is_image:
        final_message_text = (
            f'<AttachmentWidget {{"attachmentTitle": {escaped_title}, "attachmentLink": null, '
            f'"imageSrc": {escaped_attachment_link}, "caption": {escaped_caption}}} ></AttachmentWidget>'
        )
    else:
        final_message_text = (
            f'<AttachmentWidget {{"attachmentTitle": {escaped_title}, "attachmentLink": {escaped_attachment_link}, '
            f'"imageSrc": null, "caption": {escaped_caption}}} ></AttachmentWidget>'
        )

    return final_message_text, attachment, True


def update_match_for_message(sender, recipient, chat) -> None:
    if chat.is_temporary:
        return

    match = Match.get_match(sender, recipient)
    if not match.exists():
        raise MatchSendForbidden()
    match = match.first()
    if match is None:
        raise MatchSendForbidden()

    match.total_messages_counter += 1
    match.latest_interaction_at = timezone.now()
    if match.first_interaction_at is None:
        match.first_interaction_at = timezone.now()
    match.save()


def resolve_recipient_email_notification(recipient) -> bool:
    creation_time = timezone.now()
    latest_notified_message = (
        Message.objects.filter(
            recipient=recipient,
            recipient_notified=True,
        )
        .order_by("-created")
        .first()
    )

    def recipient_in_active_video_call() -> bool:
        return (
            LivekitSession.objects.filter(
                is_active=True,
            )
            .filter(
                Q(u1=recipient, u1_active=True) | Q(u2=recipient, u2_active=True),
            )
            .exists()
        )

    if latest_notified_message:
        time_since_last_notif = (creation_time - latest_notified_message.created).total_seconds()
        if time_since_last_notif > 300 and not recipient_in_active_video_call():
            send_email_background.delay("new-messages", user_id=recipient.pk)
            return True
        return False

    if not recipient_in_active_video_call():
        send_email_background.delay("new-messages", user_id=recipient.pk)
        return True
    return False


def create_and_deliver_message(
    *,
    chat: Chat,
    sender: User,
    recipient: User,
    text: str = "",
    file=None,
    auto_mark_read: bool = False,
    send_websocket: bool = True,
    send_websocket_to_sender: bool = False,
    update_match: bool = True,
    send_email: bool = True,
    send_push_notification: bool = True,
) -> Message:
    attachment = None
    final_message_text = text
    is_parsable = False

    if file:
        final_message_text, attachment, is_parsable = process_message_attachment(file, text)

    if update_match:
        update_match_for_message(sender, recipient, chat)

    recipient_was_email_notified = resolve_recipient_email_notification(recipient) if send_email else auto_mark_read

    message = Message.objects.create(
        chat=chat,
        sender=sender,
        recipient=recipient,
        read=auto_mark_read,
        recipient_notified=recipient_was_email_notified,
        text=final_message_text,
        attachments=attachment,
        parsable_message=is_parsable,
    )

    if update_match and not chat.is_temporary:
        match = Match.get_match(sender, recipient).first()
        if match is not None:
            match.confirm_from_mutual_contact()

    if send_websocket:
        from chat.consumers.messages import NewMessage

        serialized_message = MessageSerializer(message).data
        NewMessage(
            message=serialized_message,
            chat_id=str(chat.uuid),
            meta_chat_obj=ChatSerializer(chat, context={"user": recipient}).data,
        ).send(str(recipient.uuid))

        if send_websocket_to_sender:
            NewMessage(
                message=serialized_message,
                chat_id=str(chat.uuid),
                meta_chat_obj=ChatSerializer(chat, context={"user": sender}).data,
                sender_is_self=True,
            ).send(str(sender.uuid))

    if send_push_notification:
        push_notification_background.delay(
            recipient.pk,
            title=f"{sender.first_name} {sender.last_name}",
            description=message.text,
            notification_type=PushNotificationType.CHAT,
            path=f"/app/chat/{str(chat.uuid)}",
            group=f"chat:{str(chat.uuid)}",
        )

    return message
