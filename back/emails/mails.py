from dataclasses import dataclass
from rest_framework import serializers
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.template.loader import render_to_string
from back.utils import dataclass_as_dict
from .templates import inject_template_data
from .models import EmailLog
from .templates import (
    WelcomeTemplateParamsDefaults,
    WelcomeTemplateMail,
    PasswordResetEmailDefaults,
    PasswordResetEmailTexts,
    # Currently we are using the same template as weclone
    # so MatchFoundEmailTexts has no Defaults
    MatchFoundEmailTexts,
    SorryWeStillNeedALittleMail,
    NewServerMail,
    RAWTemplateMail
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
class PwResetMailParams:
    password_reset_url: str


@dataclass
class NewServerMailParams:
    pass


# Register all templates and their serializers here
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
        # subject =
        template="emails/welcome.html",
        params=WelcomeEmailParams,
        texts=WelcomeTemplateMail,
        defaults=WelcomeTemplateParamsDefaults
    ),
    MailMeta(  # Match Found Email !
        name="match",
        template="emails/welcome.html",  # TODO: get correct template
        # subject = TODO
        params=MatchMailParams,
        texts=MatchFoundEmailTexts,
        defaults=WelcomeTemplateParamsDefaults
    ),
    MailMeta(
        name="password_reset",
        # subject =
        template="emails/password_reset.html",
        params=PwResetMailParams,
        texts=PasswordResetEmailTexts,
        defaults=PasswordResetEmailDefaults
    ),
    MailMeta(
        name="new_server",
        # subject =
        template="emails/base_with_social_banner.html",
        params=NewServerMailParams,
        texts=NewServerMail,
        defaults=NewServerMail
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
        sender=None):
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
        log = EmailLog.objects.create(
            sender=get_base_management_user(),
            receiver=usr_ref,
            template=mail_data.name,
            data=dict(
                params=dataclass_as_dict(mail_params),
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
            mail.send(fail_silently=False)
            log.sucess = True
        except Exception as e:
            # Now we mark the email logs as errored
            expt = str(e)
            _data = log.data
            _data['error'] = expt
            log.data = _data
        log.save()  # Saves the error after it happended ( or stores sending success )
        if expt and raise_exception:  # If there was an error we can raise it now!
            raise Exception(expt)
