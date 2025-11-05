from uuid import uuid4

from django.conf import settings
from django.db import models
from multiselectfield import MultiSelectField
from rest_framework import serializers

from .user import User


class UnsubscibeOptions(models.TextChoices):
    interview_requests = "interview_requests"
    survery_requests = "survery_requests"
    finish_reminders = "finish_reminders"
    event_announcement = "event_announcement"


class EmailSettings(models.Model):
    hash = models.UUIDField(default=uuid4, editable=False)

    email_verification_reminder1 = models.BooleanField(default=False)
    user_form_unfinished_reminder1 = models.BooleanField(default=False)
    user_form_unfinished_reminder2 = models.BooleanField(default=False)

    # email lists the user is currently unsubscribed from
    # TODO: depricated, old email api
    unsubscibed_options = MultiSelectField(
        choices=UnsubscibeOptions.choices, max_choices=20, max_length=500, default=[]
    )

    unsubscribed_categories = models.JSONField(default=list)

    def has_unsubscribed(self, option: UnsubscibeOptions):
        return option in self.unsubscibed_options

    def send_user_form_unfinished_reminder1(self, user):
        if self.user_form_unfinished_reminder1:
            return  # already sent

        self.user_form_unfinished_reminder1 = True

        # send groupmail function automaticly checks if users have unsubscribed!
        # we still mark email verification reminder 1 as True, since we at least tried to send it,
        # never wanna send twice! Not even **try** twice!
        # send the mail
        user.send_email_v2("unfinished_user_form_1")

        self.save()

    def send_user_form_unfinished_reminder2(self, user):
        if self.user_form_unfinished_reminder2:
            return  # already sent


        self.user_form_unfinished_reminder2 = True

        # send groupmail function automaticly checks if users have unsubscribed!
        # we still mark email verification reminder 1 as True, since we at least tried to send it,
        # never wanna send twice! Not even **try** twice!
        user.send_email_v2("verify-email")
        self.save()

    def send_email_verification_reminder1(self, user):
        if self.email_verification_reminder1:
            return  # already sent

        self.email_verification_reminder1 = True

        # send groupmail function automaticly checks if users have unsubscribed!
        # we still mark email verification reminder 1 as True, since we at least tried to send it,
        # never wanna send twice! Not even **try** twice!

        # send the mail
        user.send_email_v2("verify-email")
        self.save()


def create_email_settings() -> EmailSettings:
    ems = EmailSettings.objects.create()
    return ems.id


class Settings(models.Model):
    """Stores the language code of the selected frontend language"""

    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Key...

    language = models.CharField(max_length=20, default="en")

    email_settings = models.OneToOneField(EmailSettings, on_delete=models.CASCADE, default=create_email_settings)


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settings
        fields = "__all__"


class SelfSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settings
        fields = ["language"]
