from enum import StrEnum
from typing import assert_never
from uuid import uuid4

from celery import current_app
from chat.models import Chat, ChatSerializer, Message, MessageSerializer
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import Q
from emails.api.send_email import send_template_email
from firebase_admin import messaging
from rest_framework import serializers
from webpack_loader.utils import get_static

from back import utils
from management.models.mobile_device import MobileDevice
from management.models.notifications import Notification
from management.permissions import ManagementPermission


class PushNotificationType(StrEnum):
    CHAT = "chat"
    MATCH = "match"
    ANNOUNCEMENT = "announcement"

    @property
    def notification_channel(self) -> str:
        """The notification channel used for this notification type."""
        match self:
            case PushNotificationType.CHAT:
                return "conversations"
            case PushNotificationType.MATCH:
                return "conversations"
            case PushNotificationType.ANNOUNCEMENT:
                return "announcements"
        assert_never(self)

    @property
    def android_priority(self) -> str:
        """FCM delivery priority: 'high' skips Doze batching, 'normal' can be delayed."""
        match self:
            case PushNotificationType.CHAT:
                return "high"
            case PushNotificationType.MATCH:
                return "high"
            case PushNotificationType.ANNOUNCEMENT:
                return "normal"
        assert_never(self)

    @property
    def profile_field(self) -> str:
        """The `Profile` boolean field for this notification type."""
        match self:
            case PushNotificationType.CHAT:
                return "push_notifications_chats_enabled"
            case PushNotificationType.MATCH:
                return "push_notifications_matches_enabled"
            case PushNotificationType.ANNOUNCEMENT:
                return "push_notifications_announcements_enabled"
        assert_never(self)


def bulk_push_devices(notification_type: PushNotificationType):
    """All active devices of users opted in to this notification type."""
    notifications_enabled_field = f"user__profile__{notification_type.profile_field}"
    return MobileDevice.objects.filter(
        active=True,
        user__profile__push_notifications_enabled=True,
        **{notifications_enabled_field: True},
    )


def send_bulk_push_notification(
    title: str,
    description: str,
    notification_type: PushNotificationType,
    path: str | None = None,
    group: str | None = None,
):
    bulk_push_devices(notification_type).send_message(
        build_push_message(title, description, notification_type, path, group)
    )


def build_push_message(
    title: str,
    description: str,
    notification_type: PushNotificationType,
    path: str | None = None,
    group: str | None = None,
) -> messaging.Message:
    notification_type = PushNotificationType(notification_type)

    data = {}
    if path:
        data["path"] = path
    if group:
        data["group"] = group

    data = None if len(data.keys()) == 0 else data

    return messaging.Message(
        notification=messaging.Notification(title=title, body=description),
        data=data,
        android=messaging.AndroidConfig(
            priority=notification_type.android_priority,
            notification=messaging.AndroidNotification(channel_id=notification_type.notification_channel),
        ),
        apns=messaging.APNSConfig(
            headers={"apns-priority": "5" if notification_type.android_priority == "normal" else "10"},
            payload=messaging.APNSPayload(aps=messaging.Aps(sound="default", thread_id=group)),
        ),
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                title=title,
                body=description,
                icon=get_static("android-chrome-512x512.png", config="main_frontend"),
            ),
        ),
    )


class UserManager(BaseUserManager["User"]):
    """
    We overwrite the BaseUserManager so we can:
    - automaticly create State, Profile, Settings everytime create_user is called
    """

    def _create_user(self, email=None, password=None, **kwargs):
        # TODO: defering the import here is suboptimal, import stucture should be impoved
        # But importing them on top level will cause circular import currently
        from . import profile, settings, state

        assert email and password
        email = email.lower()
        user = self.model(email=email, **kwargs)
        user.save(using=self._db)
        user.set_password(password)
        user.save(using=self._db)
        """
        Now we create: State, Profile, Settings, creating them here ensures that they will always be present!
        All users have that even all the admin users!
        """
        state.State.objects.create(user=user)
        profile.Profile.objects.create(
            user=user,
            # We let this throw an error if fist name is not present
            # Cause it should always be present! ( Note: for admin users we offer an default)
            first_name=kwargs.get("first_name"),
            # I like calling this 'last_name' more
            second_name=kwargs.get("last_name"),
        )
        settings.Settings.objects.create(user=user)
        return user

    def create_user(self, email, password, **kwargs):
        kwargs["is_staff"] = False
        kwargs["is_superuser"] = False
        return self._create_user(email=email, password=password, **kwargs)

    def create_superuser(self, email, password, **kwargs):
        kwargs["is_staff"] = True
        kwargs["is_superuser"] = True
        kwargs["first_name"] = kwargs.pop("first_name")
        kwargs["last_name"] = kwargs.pop("second_name")
        usr = self._create_user(email=email, password=password, **kwargs)

        # Superuses cant be bothered to verify their email:
        usr.state.check_email_auth_pin(usr.state.email_auth_pin)
        return usr


class User(AbstractUser):
    """
    The default django user model.
    It is recommended to extend this class
    make small modifications if required
    in the settings we set this via 'AUTH_USER_MODEL'
    """

    # Legacy identifier kept for backward compatibility.
    hash = models.CharField(max_length=100, blank=True, unique=True, default=utils._double_uuid)  # type: ignore

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)

    objects: UserManager = UserManager()  # Register the custom user manager

    # Stores the legacy backend hash before UUID becomes the canonical identifier.
    old_backend_user_hash = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # Deprecated legacy field from early migrations. Kept to avoid breaking historical data.
    old_backend_user_h256_pk = models.CharField(max_length=255, blank=True, null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original_username = self.username

    @property
    def state(self):
        from . import state

        return state.State.objects.get(user=self)

    @property
    def profile(self):
        from . import profile

        return profile.Profile.objects.get(user=self)

    @property
    def settings(self):
        from . import settings

        return settings.Settings.objects.get(user=self)

    @property
    def open_assigned_support_task_count(self) -> int:
        from .support_task import SupportTask

        return self.assigned_support_tasks.exclude(status=SupportTask.Status.COMPLETED).count()

    @property
    def open_related_support_task_count(self) -> int:
        from .support_task import SupportTask

        return self.related_support_tasks.exclude(status=SupportTask.Status.COMPLETED).count()

    # Not only having but also displaying the full identifier is not necessary
    def _abr_hash(self):
        return str(self.uuid)[:8]

    # This is realy only a nicer wrapper for the user form filled state
    # will display the nice check mark in admin pannel
    def is_user_form_filled(self):
        _state = self.state
        return _state.user_form_state == _state.UserFormStateChoices.FILLED

    is_user_form_filled.boolean = True

    def save(self, *args, **kwargs):
        if self.email != self.__original_username:
            # Then the email of that user was changed!
            # This means we have to update the username too!
            self.username = self.email
        super().save(*args, **kwargs)
        self.__original_username = self.username

    def get_notifications(self, state):
        """Returns a list of matches"""

        notifications = Notification.objects.filter(user=self).exclude(state=Notification.NotificationState.DELETED)

        if state != "all":
            notifications = notifications.filter(state=state)
        else:
            notifications = notifications.filter(
                state__in=[Notification.NotificationState.UNREAD, Notification.NotificationState.READ]
            )
        return notifications.order_by("-created_at")

    def grant_permission(self, permission: ManagementPermission) -> bool:
        permission_obj = permission.get_permission_object()
        if permission_obj is None:
            return False
        had_permission = self.has_perm(permission)
        self.user_permissions.add(permission_obj)
        if permission == ManagementPermission.RECEIVES_FULL_USER_ACCESS and not had_permission:
            current_app.send_task(  # pyright: ignore[reportCallIssue]
                "management.tasks.sync_full_user_access_for_manager",
                kwargs={"manager_user_id": self.pk},
            )
        return True

    def revoke_permission(self, permission: ManagementPermission) -> bool:
        permission_obj = permission.get_permission_object()
        if permission_obj is None:
            return False
        self.user_permissions.remove(permission_obj)
        return True

    def grant_management_access(self, managed_user: "User", granted_by: "User | None" = None) -> bool:
        from management.models.management_access_grant import ManagementAccessGrant

        _, created = ManagementAccessGrant.objects.update_or_create(
            manager=self,
            managed_user=managed_user,
            defaults={
                "is_active": True,
                "granted_by": granted_by,
            },
        )
        return created

    def revoke_management_access(self, managed_user: "User") -> bool:
        from management.models.management_access_grant import ManagementAccessGrant

        updated = ManagementAccessGrant.objects.filter(
            manager=self,
            managed_user=managed_user,
            is_active=True,
        ).update(is_active=False)
        return updated > 0

    def has_management_access(self, managed_user: "User") -> bool:
        if self.is_staff:
            return True
        from management.models.management_access_grant import ManagementAccessGrant

        return ManagementAccessGrant.objects.filter(
            manager=self,
            managed_user=managed_user,
            is_active=True,
        ).exists()

    def managed_users_queryset(self, active_only: bool = True):
        qs = User.objects.filter(
            Q(
                management_accesses_received__manager=self,
                management_accesses_received__is_active=True,
            )
        ).distinct()
        if active_only:
            qs = qs.filter(is_active=True)
        return qs

    # DEPRECATED, use send_notification instead
    def notification(self, title, description, show_toast=True):
        """Notifies the user about a notification via websockets"""
        from chat.consumers.messages import NotificationMessage

        from management.models.notifications import NotificationSerializer

        notification = Notification.objects.create(user=self, title=title, description=description)

        NotificationMessage(notification=NotificationSerializer(notification).data, show_toast=show_toast).send(
            str(self.uuid)
        )

    def send_notification(
        self,
        title: str,
        description: str,
        notification_type: PushNotificationType,
        persist=False,
        path=None,
        group=None,
    ):
        if persist:
            Notification.objects.create(user=self, title=title, description=description)

        self.push_notification(
            title=title,
            description=description,
            notification_type=notification_type,
            path=path,
            group=group,
        )

    def push_notification(
        self,
        title: str,
        description: str,
        notification_type: PushNotificationType | str,
        path: str | None = None,
        group: str | None = None,
    ):
        """Send a push notification to all of the user's devices."""
        notification_type = PushNotificationType(notification_type)
        self.push_devices(notification_type).send_message(
            build_push_message(title, description, notification_type, path, group)
        )

    def push_devices(self, notification_type: PushNotificationType | str | None = None):
        if not self.profile.push_notifications_enabled:
            return MobileDevice.objects.none()
        if notification_type is not None:
            # can be serialized by celery, so cast it back
            notification_type = PushNotificationType(notification_type)
            if not getattr(self.profile, notification_type.profile_field):
                return MobileDevice.objects.none()

        devices = MobileDevice.objects.filter(user=self, active=True)
        # send to online devices only if any exist, otherwise send to all
        online = devices.online()
        return online if online.exists() else devices

    def sms(self, send_initator, message, dont_send=False, skip_reason="skipped"):
        """ "Sends SMS to User if user has SMS Notification allowed and valid Phone number"""
        import json

        from back.utils import CoolerJson
        from twilio.rest import Client

        from management.models.sms import SmsModel, SmsSerializer

        if settings.DISABLE_SMS_SENDING:
            return 403

        if dont_send:
            response = SmsModel.objects.create(
                recipient=self,
                send_initator=send_initator,
                message=message,
                success=False,
                twilio_response=json.dumps(
                    {
                        "status": skip_reason,
                    }
                ),
            )
            return 200

        if self.profile.notify_channel == "sms" and self.profile.phone_mobile != "":
            response = SmsModel.objects.create(recipient=self, send_initator=send_initator, message=message)
            try:
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                twilio_response = client.messages.create(
                    body=message, from_=settings.TWILIO_SMS_NUMBER, to=str(self.profile.phone_mobile)
                )
                response.twilio_response = json.dumps(twilio_response.__dict__, cls=CoolerJson)
                response.success = True
                response.save()
                return SmsSerializer(response).data
            except Exception:
                response.success = False
                response.save()
                return 500
        else:
            return 403

    def change_email(self, email, send_verification_mail=True):
        """
        Can be used to change the email
        there is a problem with authentication of the changed email check `user.state.past_emails`
        The user will still be allowed to use this api to change the email back
        there is the frontend `/change_email` for logged-in users
        so if someone falsely changes their mail they can change it back
        & user will be automatically redirected to `/mailverify/`
        which has a button `change-email` which redirects to `/change_email`
        """
        from ..api.user import ChangeEmailSerializer

        # We do an additional email serialization here!
        _s = ChangeEmailSerializer(data=dict(email=email))  # type: ignore
        _s.is_valid(raise_exception=True)
        prms = _s.save()

        self.state.archive_email_adress(self.email)
        self.state.regnerate_email_auth_code()  # New auth code and pin !

        # NOTE the save() method automatically detects the email change and also changes the username
        # We do this so admins can edit emails in the admin pannel and changes are reflected as expected
        # self.username = prms.email  # <- so the user can login with that email now
        self.email = prms.email.lower()
        self.save()
        if send_verification_mail:
            self.send_email("automatic-emails-u001")

    def message(
        self,
        msg,
        sender=None,
        file=None,
        *,
        apply_delivery_side_effects=False,
        auto_mark_read=False,
        send_message_incoming=True,
        parsable_message=True,
        send_message_incoming_to_sender=False,
    ):
        """
        Sends the users a chat message
        theoreticly this could be used to send a message from any sender
        """
        from chat.helpers import create_and_deliver_message

        from ..controller import get_base_management_user

        if not sender:
            # TODO: the management user should be inferred on per user basis!
            sender = get_base_management_user()

        chat = Chat.get_or_create_chat(sender, self)

        if apply_delivery_side_effects:
            return create_and_deliver_message(
                chat=chat,
                sender=sender,
                recipient=self,
                text=msg,
                file=file,
                auto_mark_read=auto_mark_read,
                send_websocket=(not auto_mark_read) or send_message_incoming,
                send_websocket_to_sender=send_message_incoming_to_sender,
            )

        message = Message.objects.create(
            chat=chat,
            sender=sender,
            recipient=self,
            read=auto_mark_read,
            recipient_notified=auto_mark_read,
            text=msg,
            parsable_message=parsable_message,
        )

        serialized_message = MessageSerializer(message).data

        if (not auto_mark_read) or send_message_incoming:
            from chat.consumers.messages import NewMessage

            NewMessage(
                message=serialized_message,
                chat_id=str(chat.uuid),
                meta_chat_obj=ChatSerializer(
                    chat,
                    context={
                        "user": self,
                    },
                ).data,
            ).send(str(self.uuid))
            if send_message_incoming_to_sender:
                NewMessage(
                    message=serialized_message,
                    chat_id=str(chat.uuid),
                    meta_chat_obj=ChatSerializer(
                        chat,
                        context={
                            "user": sender,
                        },
                    ).data,
                    sender_is_self=True,
                ).send(str(sender.uuid))
        return message

    def send_email(self, template_name, match_id=None, proposed_match_id=None, context={}):
        send_template_email(
            template_name, user_id=self.pk, match_id=match_id, proposed_match_id=proposed_match_id, context=context
        )


class UserSerializer(serializers.ModelSerializer):
    is_admin = serializers.SerializerMethodField()

    def get_is_admin(self, obj):
        return obj.is_staff

    class Meta:
        model = User
        fields = "__all__"


class SelfUserSerializer(UserSerializer):
    class Meta:
        model = User
        fields = ["email", "uuid", "is_admin"]


class CensoredUserSerializer(UserSerializer):
    class Meta:
        model = User
        fields = ["uuid", "is_admin"]
        fields = ["uuid", "is_admin"]
