from dataclasses import dataclass
from rest_framework import serializers
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.template.loader import render_to_string
from back.utils import dataclass_as_dict
from emails.templates import inject_template_data
from emails.templates import (
    WelcomeTemplateParamsDefaults,
    WelcomeTemplateMail,
    PasswordResetEmailDefaults,
    PasswordResetEmailTexts,
    UnfinishedUserForm1Messages,
    UnfinishedUserForm2Messages,
    ConfirmMatchMail1Texts,
    ConfirmMatchMail2Texts,
    MatchExpiredMailTexts,
    EmailVerificationReminderMessages,
    StillInContactMessages,
    MatchRejectedEmailTexts,
    InterviewInvitation,
    GeneralSurveyMail,
    GeneralSurveyMail_0311,
    ImpulsBeitraegeMail,
    ImpulsBeitraegeMail2,
    CommunityGetTogetherInvitation,
    CommunityGetTogetherInvitation130624,
    TrainingSeriesInvitation,
    # Currently we are using the same template as weclone
    # so MatchFoundEmailTexts has no Defaults
    SurveyInvitationAniq2,
    NewUnreadMessages,
    MatchFoundEmailTexts,
    CulturalAwarenessInvitation,
    CultureDimensionsLectureInvitationToday,
    SorryWeStillNeedALittleMail,
    NewServerMail,
GermanImprovementBabbelInvitation,
    RAWTemplateMail,
    UserSurveyInvitationEmailNatalia,
    UserInterviewRequestEmail,
    AccountDeletedEmailTexts,
    BabbelSubscriptionMail_Winner,
    CommunityGetTogetherInvitation120624,
    CommunityGetTogetherInvitationToday
)
from django.core.mail import EmailMessage
import json
import base64
import zlib

"""
This file contains a dataclass for every email
This way we get typesafety for all emails,
and it is easy to tell which parameters are available
"""
# Pass


class MailDataNotFoundErr(Exception):
    pass

@dataclass
class GermanImprovementBabbelInvitationParams:
    first_name: str
    link_url: str
    unsubscribe_url1: str

@dataclass
class BabbelSubscriptionMailWinnerParams:
    first_name: str
    unsubscribe_url1: str
    
@dataclass
class CultureDimensionsLectureInvitationTodayParams:
    first_name: str

@dataclass
class SurveyInvitation2AniqParams:
    first_name: str
    link_url: str
    unsubscribe_url1: str

@dataclass
class ImpulseBeitraegeParams:
    first_name: str
    link_url: str
    unsubscribe_url1: str

@dataclass
class ImpulseBeitraegeParams2:
    first_name: str
    link_url: str
    unsubscribe_url1: str

@dataclass
class CommunityGetTogetherMailParams:
    first_name: str
    
@dataclass
class CommunityGetTogetherMailParams120624:
    first_name: str
    unsubscribe_url1: str
    
@dataclass
class CommunityGetTogetherInvitationTodayParams:
    first_name: str

@dataclass
class CulturalAwarenessInvitationParams:
    first_name: str
    
@dataclass
class AccountDeletedEmailParams:
    first_name: str
    registration_link_url : str = 'https://little-world.org/sign-up'
    
@dataclass
class TrainingInvitationParams:
    first_name: str
    
@dataclass
class SurveryInvitation3Natalia:
    first_name: str
    unsubscribe_url1: str

@dataclass
class StillInContactParams:
    first_name: str
    partner_first_name: str
    
@dataclass
class MatchRejectedEmailParams:
    first_name: str
    partner_first_name: str
    
@dataclass
class CommunityGetTogetherInvitation130624Params:
    first_name: str
    
    
@dataclass
class GeneralSurveryMail_03_11_Params:
    first_name: str
    link_url: str
    unsubscribe_url1: str
    
@dataclass
class GeneralSurveryMailParams:
    first_name: str
    link_url: str
    unsubscribe_url1: str


@dataclass
class MatchConfirmationMail1Params:
    first_name: str
    match_first_name: str
    team_phone: str = '015234777471'
    team_email: str = 'support@little-world.com'

@dataclass
class MultiUserInterviewRequestEmail_5:
    first_name: str
    unsubscribe_url1: str
    
    
@dataclass
class InterviewInvitationParams:
    first_name: str
    email_aniqa: str
    link_url: str
    unsubscribe_url1: str

@dataclass
class MatchConfirmationMail2Params:
    first_name: str
    match_first_name: str
    team_phone: str = '015234777471'
    team_email: str = 'support@little-world.com'

@dataclass
class MatchExpiredMailParams:
    first_name: str
    match_first_name: str
    team_phone: str = '015234777471'
    team_email: str = 'support@little-world.com'

@dataclass
class UnfinishedUserForm1Params:
    first_name: str
    unsubscribe_url1: str
    team_phone: str = '015234777471'
    team_email: str = 'support@little-world.com'


@dataclass
class UnfinishedUserForm2Params:
    first_name: str
    unsubscribe_url1: str
    team_phone: str = '015234777471'
    team_email: str = 'support@little-world.com'

@dataclass
class UnfinishedEmailVerificationParams:
    first_name: str
    unsubscribe_url1: str

@dataclass
class RAWTemplateMailParams:
    subject_header_text: str = ''
    greeting: str = ''
    content_start_text: str = ''
    content_body_text: str = ''
    link_box_text: str = ''
    button_text: str = ''
    button_link: str = ''
    below_link_text: str = ''
    footer_text: str = ''
    goodbye: str = ''
    goodbye_name: str = ''


@dataclass
class MailMeta:
    name: str
    template: str
    params: object
    defaults: object
    texts: object
    
    def serialized(self):
        return {
            "name": self.name,
            "template": self.template,
        }


@dataclass
class WelcomeEmailParams:
    # We only talk to people in first name these days
    first_name: str
    verification_code: str
    verification_url: str


@dataclass
class MatchMailParams:
    first_name: str
    match_first_name: str
    profile_link_url: str


@dataclass
class NewUreadMessagesParams:
    first_name: str


@dataclass
class PwResetMailParams:
    password_reset_url: str


@dataclass
class NewServerMailParams:
    placeholder: str = "placeholder"


# Register all templates and their serializers here
# TODO: make email subject part of the template
templates = [
    MailMeta(
        name="raw",
        template="emails/welcome.html",
        params=RAWTemplateMailParams,
        defaults=WelcomeTemplateParamsDefaults,
        texts=RAWTemplateMail
    ),
    MailMeta(  # Welcome & Email verification !
        name="welcome",
        template="emails/welcome.html",
        params=WelcomeEmailParams,
        texts=WelcomeTemplateMail,
        defaults=WelcomeTemplateMail
    ),
    MailMeta(  # Match Found Email !
        name="match",
        template="emails/welcome.html",
        params=MatchMailParams,
        texts=MatchFoundEmailTexts,
        defaults=MatchFoundEmailTexts
    ),
    MailMeta(  # Interview request ** special email **
        name="interview",
        template="emails/welcome.html",
        params=InterviewInvitationParams,
        texts=InterviewInvitation,
        defaults=InterviewInvitation
    ),
    MailMeta(
        name="password_reset",
        template="emails/password_reset.html",
        params=PwResetMailParams,
        texts=PasswordResetEmailTexts,
        defaults=PasswordResetEmailDefaults
    ),
    MailMeta(
        name="match_resolved",
        template="emails/welcome.html",
        params=MatchRejectedEmailParams,
        texts=MatchRejectedEmailTexts,
        defaults=MatchRejectedEmailTexts,
    ),
    MailMeta(
        name="new_server",
        template="emails/base_with_social_banner.html",
        params=NewServerMailParams,
        texts=NewServerMail,
        defaults=NewServerMail
    ),
    MailMeta(
        name="new_messages",
        template="emails/welcome.html",
        params=NewUreadMessagesParams,
        texts=NewUnreadMessages,
        defaults=NewUnreadMessages
    ),
    MailMeta(
        name="email_unverified",
        template="emails/welcome.html",
        params=UnfinishedEmailVerificationParams,
        texts=EmailVerificationReminderMessages,
        defaults=EmailVerificationReminderMessages
    ),
    MailMeta(
        name="still_in_contact",
        template="emails/welcome.html",
        params=StillInContactParams,
        texts=StillInContactMessages,
        defaults=StillInContactMessages
    ),
    MailMeta(
        name="unfinished_user_form_1",
        template="emails/welcome.html",
        params=UnfinishedUserForm1Params,
        texts=UnfinishedUserForm1Messages,
        defaults=UnfinishedUserForm1Messages
    ),
    MailMeta(
        name="unfinished_user_form_2",
        template="emails/welcome.html",
        params=UnfinishedUserForm2Params,
        texts=UnfinishedUserForm2Messages,
        defaults=UnfinishedUserForm2Messages
    ),
    MailMeta(
        name="confirm_match_mail_1",
        template="emails/welcome.html",
        params=MatchConfirmationMail1Params,
        texts=ConfirmMatchMail1Texts,
        defaults=ConfirmMatchMail1Texts
    ),
    MailMeta(
        name="confirm_match_mail_2",
        template="emails/welcome.html",
        params=MatchConfirmationMail2Params,
        texts=ConfirmMatchMail2Texts,
        defaults=ConfirmMatchMail2Texts
    ),
    MailMeta(
        name="general_interview",
        template="emails/welcome_reversed.html",
        params=GeneralSurveryMailParams,
        texts=GeneralSurveyMail,
        defaults=GeneralSurveyMail
    ),
    MailMeta(
        name="general_interview_03_11",
        template="emails/welcome_reversed.html",
        params=GeneralSurveryMail_03_11_Params,
        texts=GeneralSurveyMail_0311,
        defaults=GeneralSurveyMail_0311
    ),
    MailMeta(
        name="confirm_match_expired_mail_1",
        template="emails/welcome.html",
        params=MatchExpiredMailParams,
        texts=MatchExpiredMailTexts,
        defaults=MatchExpiredMailTexts
    ),
    MailMeta(
        name="survey_aniq_2",
        template="emails/welcome.html",
        params=SurveyInvitation2AniqParams,
        texts=SurveyInvitationAniq2,
        defaults=SurveyInvitationAniq2
    ),
    MailMeta(
        name="survey3_natalia",
        template="emails/welcome.html",
        params=SurveryInvitation3Natalia,
        texts=UserSurveyInvitationEmailNatalia,
        defaults=UserSurveyInvitationEmailNatalia
    ),
    MailMeta(
        name="multi_user_interview_request_5",
        template="emails/welcome.html",
        params=MultiUserInterviewRequestEmail_5,
        texts=UserInterviewRequestEmail,
        defaults=UserInterviewRequestEmail
    ),
    MailMeta(
        name="account_deleted",
        template="emails/welcome.html",
        params=AccountDeletedEmailParams,
        texts=AccountDeletedEmailTexts,
        defaults=AccountDeletedEmailTexts
    ),
    MailMeta(
        name="impuls_beitraege",
        template="emails/welcome.html",
        params=ImpulseBeitraegeParams,
        texts=ImpulsBeitraegeMail,
        defaults=ImpulsBeitraegeMail
    ),
    MailMeta(
        name="impuls_beitraege2",
        template="emails/welcome.html",
        params=ImpulseBeitraegeParams2,
        texts=ImpulsBeitraegeMail2,
        defaults=ImpulsBeitraegeMail2
    ),
    MailMeta(
        name="babbel_subscription_winner",
        template="emails/welcome.html",
        params=BabbelSubscriptionMailWinnerParams,
        texts=BabbelSubscriptionMail_Winner,
        defaults=BabbelSubscriptionMail_Winner
    ),
    MailMeta(
        name="german_improvement_babbel_invitation",
        template="emails/survey.html",
        params=GermanImprovementBabbelInvitationParams,
        texts=GermanImprovementBabbelInvitation,
        defaults=GermanImprovementBabbelInvitation
    ),
    MailMeta(
        name="community_get_together",
        template="emails/welcome.html",
        params=CommunityGetTogetherMailParams,
        texts=CommunityGetTogetherInvitation,
        defaults=CommunityGetTogetherInvitation
    ),
    MailMeta(
        name="training_series",
        template="emails/welcome.html",
        params=TrainingInvitationParams,
        texts=TrainingSeriesInvitation,
        defaults=TrainingSeriesInvitation
    ),
    MailMeta(
        name="cultural_awareness",
        template="emails/welcome.html",
        params=CulturalAwarenessInvitationParams,
        texts=CulturalAwarenessInvitation,
        defaults=CulturalAwarenessInvitation
    ),
    MailMeta(
        name="community_get_together_120624",
        template="emails/welcome.html",
        params=CommunityGetTogetherMailParams120624,
        texts=CommunityGetTogetherInvitation120624,
        defaults=CommunityGetTogetherInvitation120624
    ),
    MailMeta(
        name="community_get_together_today",
        template="emails/welcome.html",
        params=CommunityGetTogetherInvitationTodayParams,
        texts=CommunityGetTogetherInvitationToday,
        defaults=CommunityGetTogetherInvitationToday
    ),
    MailMeta(
        name="culture_dimensions_lecture_today",
        template="emails/welcome.html",
        params=CultureDimensionsLectureInvitationTodayParams,
        texts=CultureDimensionsLectureInvitationToday,
        defaults=CultureDimensionsLectureInvitationToday
    ),
    MailMeta(
        name="community_get_together_130624",
        template="emails/welcome.html",
        params=CommunityGetTogetherInvitation130624Params,
        texts=CommunityGetTogetherInvitation130624,
        defaults=CommunityGetTogetherInvitation130624
    )
]


def get_mail_data_by_name(name) -> MailMeta:
    for t in templates:
        if t.name == name:
            return t
    raise MailDataNotFoundErr(_("Mail data with name not found"))


def encode_mail_params(params_raw):
    return base64.urlsafe_b64encode(zlib.compress(
        bytes(json.dumps(params_raw), 'utf-8'))).decode()


def decode_mail_params(pramas_encoded):
    return json.loads(zlib.decompress(
        base64.urlsafe_b64decode(pramas_encoded.encode())).decode())


def send_email(
        subject: str,
        recivers: list,  # email adresses!
        mail_data: MailMeta,
        mail_params: object,
        attachments=[],
        raise_exception=False,
        sender=None,
        emulated_send=False):
    """
    Sends any mail we do this within a celery task to avoid runtime errors
    This does not send a messages to all receivers at the same time, 
    it sends one email per receiver
    """
    from management.controller import get_base_management_user, get_user_by_email
    if sender is None:
        sender = settings.DEFAULT_FROM_EMAIL

    for to in recivers:

        usr_ref = None
        try:
            usr_ref = get_user_by_email(to)
        except:
            print(
                f"User '{to}' doesn't seem to be registered, sending mail anyways")

        # First create the mail log, if sending fails afterwards we sill have a log!
        from emails.models import EmailLog
        log = EmailLog.objects.create(
            sender=get_base_management_user(),
            receiver=usr_ref,
            template=mail_data.name,
            data=dict(
                params=dataclass_as_dict(mail_params),
                subject=str(subject),
                sender_str=str(sender),
                recivers_str=",".join(recivers)
            )
        )

        expt = None
        try:
            params_injected_text = inject_template_data(
                dataclass_as_dict(mail_data.texts), dataclass_as_dict(mail_params))
            html = render_to_string(mail_data.template, params_injected_text)

            mail = EmailMessage(
                subject=subject,
                body=html,
                from_email=sender,
                to=[to],
            )
            mail.content_subtype = "html"
            for attachment in attachments:
                mail.attach_file(attachment)
            if not emulated_send:
                mail.send(fail_silently=False)
                log.sucess = True
            else:
                log.data['emulated_send'] = True
        except Exception as e:
            # Now we mark the email logs as errored
            expt = str(e)
            _data = log.data
            _data['error'] = expt
            log.data = _data
        log.save()  # Saves the error after it happended ( or stores sending success )
        if expt and raise_exception:  # If there was an error we can raise it now!
            raise Exception(expt)
