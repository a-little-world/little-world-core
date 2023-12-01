from django.db import models
from rest_framework import serializers
from .user import User
from multiselectfield import MultiSelectField
from uuid import uuid4
from emails import mails


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
    unsubscibed_options = MultiSelectField(
        choices=UnsubscibeOptions.choices, max_choices=20, max_length=500, default=[]
    )
    
    def has_unsubscribed(self, option: UnsubscibeOptions):
        return option in self.unsubscibed_options

    def send_user_form_unfinished_reminder1(self, user):
        if self.user_form_unfinished_reminder1: 
            return # already sent

        from management import controller
        self.user_form_unfinished_reminder1 = True
        # send groupmail function automaticly checks if users have unsubscribed!
        # we still mark email verification reminder 1 as True, since we at least tried to send it, 
        # never wanna send twice! Not even **try** twice!
        def get_params(user):
            return mails.UnfinishedUserForm1Params(
                first_name=user.profile.first_name,
                unsubscribe_url1="" # filled automatically
            )
        # send the mail
        controller.send_group_mail(
            users=[user],
            subject="Umfrage beenden für Bekanntschaften aus aller Welt",
            mail_name="unfinished_user_form_1",
            mail_params_func=get_params,
            unsubscribe_group=UnsubscibeOptions.finish_reminders,
            emulated_send=True # TODO Just debug for now
        )
        
        self.save()

    def send_user_form_unfinished_reminder2(self, user):
        if self.user_form_unfinished_reminder2:
            return # already sent

        from management import controller
        self.user_form_unfinished_reminder2 = True
        # send groupmail function automaticly checks if users have unsubscribed!
        # we still mark email verification reminder 1 as True, since we at least tried to send it, 
        # never wanna send twice! Not even **try** twice!
        def get_params(user):
            return mails.UnfinishedUserForm2Params(
                first_name=user.profile.first_name,
                unsubscribe_url1="" # filled automatically
            )
        # send the mail
        controller.send_group_mail(
            users=[user],
            subject="Umfrage beenden für Bekanntschaften aus aller Welt",
            mail_name="unfinished_user_form_2",
            mail_params_func=get_params,
            unsubscribe_group=UnsubscibeOptions.finish_reminders,
            emulated_send=True # TODO Just debug for now
        )
        
        self.save()
    
    def send_email_verification_reminder1(self, user):
        if self.email_verification_reminder1: 
            return # already sent
        from management import controller

        self.email_verification_reminder1 = True
        # send groupmail function automaticly checks if users have unsubscribed!
        # we still mark email verification reminder 1 as True, since we at least tried to send it, 
        # never wanna send twice! Not even **try** twice!
        def get_params(user):
            return mails.UnfinishedEmailVerificationParams(
                first_name=user.profile.first_name,
                unsubscribe_url1="" # filled automatically
            )
        # send the mail
        controller.send_group_mail(
            users=[user],
            subject="Bitte bestätige deine E-Mail-Adresse für Little World",
            mail_name="email_unverified",
            mail_params_func=get_params,
            unsubscribe_group=UnsubscibeOptions.finish_reminders,
            emulated_send=True # TODO Just debug for now
        )
        
        self.save()

def create_email_settings() -> EmailSettings:
    ems = EmailSettings.objects.create()
    return ems.id
    

class Settings(models.Model):
    """ Stores the language code of the selected frontend language """
    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Key...

    language = models.CharField(max_length=20, default="en")
    
    email_settings = models.OneToOneField(EmailSettings, on_delete=models.CASCADE, default=create_email_settings)


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settings
        fields = '__all__'


class SelfSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settings
        fields = ["language"]
