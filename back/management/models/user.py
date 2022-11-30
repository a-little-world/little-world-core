from django.db import models
from back import utils
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from rest_framework import serializers
from asgiref.sync import async_to_sync
from django.contrib.auth.models import AbstractUser, BaseUserManager


class UserManager(BaseUserManager):
    """
    We overwrite the BaseUserManager so we can: 
    - automaticly create State, Profile, Settings everytime create_user is called
    """

    def _create_user(self, email=None, password=None, **kwargs):
        # TODO: defering the import here is suboptimal, import stucture should be impoved
        # But importing them on top level will cause circular import currently
        from . import state
        from . import profile
        from . import settings
        assert email and password
        # This will redundantly store 'first_name' and 'second_name'
        # This is nice though cause we will never change these so we always know with which name they sighned up!
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
            second_name=kwargs.get("last_name")
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
    hash = models.CharField(max_length=100, blank=True,
                            unique=True, default=utils._double_uuid)  # type: ignore

    objects = UserManager()  # Register the new user manager

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

    # Not only having but also displaying the full hashes is not necessary
    def _abr_hash(self):
        return self.hash[:8]

    # This is realy only a nicer wrapper for the user form filled state
    # will display the nice check mark in admin pannel
    def is_user_form_filled(self):
        _state = self.state
        return _state.user_form_state == _state.UserFormStateChoices.FILLED
    is_user_form_filled.boolean = True

    def get_matches(self):
        """ Returns a list of matches """
        return self.state.matches.all()

    def get_notifications(self):
        """ Returns a list of matches """
        return self.state.notifications.all()

    def match(self, user):
        """
        Adds the user as match of this user 
        ( this doesn't automaticly create a match for the other user ) 
        """
        self.state.matches.add(user)

    def change_email(self, email, send_verification_mail=True):
        """
        Can be used to change the email
        there is a problem with authentication of the changed email check `user.state.past_emails`
        The user will still be allowed to use this api to change the email back
        there is the frontend `/change_email` for logged-in users 
        so if someone fasely changes their mail they can change it back
        & user will be automaticly reidrected to `/mailverify/`
        wich has a button `change-email` which redirects to `/change_email`
        """
        from emails import mails
        from ..api.user import ChangeEmailSerializer, ChangeEmailParams
        # We do an aditional email serialization here!
        _s = ChangeEmailSerializer(data=dict(email=email))  # type: ignore
        _s.is_valid(raise_exception=True)
        prms = _s.save()

        self.state.archive_email_adress(email)
        self.state.regnerate_email_auth_code()  # New auth code and pin !

        # We send the email first so if this would fail the changing of email would also fail!
        # ... so user can not easily be locked out of their account
        verifiaction_url = f"{settings.BASE_URL}/api/user/verify/email/{self.state.get_email_auth_code_b64()}"
        self.send_email(
            # We use this here so the models doesnt have to be saved jet
            overwrite_mail=prms.email,
            subject="undefined",  # TODO set!
            # TODO this should be different email!
            mail_data=mails.get_mail_data_by_name("welcome"),
            mail_params=mails.WelcomeEmailParams(
                first_name=self.profile.first_name,
                verification_url=verifiaction_url,
                verification_code=str(self.state.get_email_auth_pin())
            )
        )

        self.email = prms.email
        self.save()

    def notify(self, title=_('title'), description=_('description')):
        """
        Sends a notifcation to that user ( or rater creates a notifcation for that user )
        """
        from .notifications import Notification
        notification = Notification.objects.create(
            user=self,
            title=title,
            description=description
        )
        self.state.notifications.add(notification)
        # TODO: in the future also send a websocked 'notification' object!

    def message(self, msg, sender=None):
        """
        Sends the users a chat message
        theoreticly this could be used to send a message from any sender
        this would ofcourse require these user to have a related dialog object
        """
        from ..controller import get_base_management_user
        from chat.django_private_chat2.consumers.db_operations import save_text_message
        if not sender:
            sender = get_base_management_user()

        async_to_sync(save_text_message)(msg, sender, self)

    def send_email(self,
                   subject: str,
                   mail_data,  # Can't really typecheck MailMeta when
                   # I'm importing below TODO this can be fixed
                   mail_params: object,
                   attachments=[],
                   overwrite_mail=None):
        """
        Just a wrapper for emails.mails.send_email
        Send to a user by usr.send_email(...)
        """
        from emails.mails import send_email, MailMeta
        recivers = [overwrite_mail] if overwrite_mail else [self.email]
        send_email(
            subject=subject,
            recivers=recivers,
            mail_data=mail_data,
            mail_params=mail_params,
            attachments=attachments
        )


class UserSerializer(serializers.ModelSerializer):
    is_admin = serializers.SerializerMethodField()

    def get_is_admin(self, obj):
        return obj.is_staff

    class Meta:
        model = User
        fields = '__all__'


class SelfUserSerializer(UserSerializer):
    class Meta:
        model = User
        fields = ["email", "hash"]


class CensoredUserSerializer(UserSerializer):
    class Meta:
        model = User
        fields = ["hash", "is_admin"]
