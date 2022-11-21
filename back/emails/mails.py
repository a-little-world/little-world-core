from dataclasses import dataclass
from rest_framework import serializers
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.template.loader import render_to_string
from .models import EmailLog
from django.core.mail import EmailMessage

"""
This file contains a dataclass for every email
This way we get typesafety for all emails,
and it is easy to tell which parameters are available
"""
# Pass


class MailDataNotFoundErr(Exception):
    pass


@dataclass
class MailMeta:
    name: str
    template: str
    params: object


@dataclass
class WelcomeEmailParams:
    # We only talk to people in first name these days
    first_name: str
    verification_code: str


@dataclass
class MatchMailParams:
    first_name: str
    match_first_name: str


# Register all templates and their serializers here
templates = [
    MailMeta(
        name="welcome",
        template="emails/welcome.html",
        params=WelcomeEmailParams
    ),
    MailMeta(
        name="match",
        template="emails/welcome.html",  # TODO: get correct template
        params=MatchMailParams
    )
]


def get_mail_data_by_name(name) -> MailMeta:
    for t in templates:
        if t.name == name:
            return t
    raise MailDataNotFoundErr(_("Mail data with name not found"))


def send_email(
        subject: str,
        recivers: list,  # email adresses!
        mail_data: MailMeta,
        mail_params: object,
        attachments=[],
        sender=settings.MANAGEMENT_USER_MAIL):
    """
    Sends any mail we do this within a celery task to avoid runtime errors
    This does not send a messages to all receivers at the same time, 
    it sends one email per receiver
    """
    from management.controller import get_base_management_user, get_user_by_email
    for to in recivers:

        # First create the mail log, if sending fails afterwards we sill have a log!
        log = EmailLog.objects.create(
            sender=get_base_management_user(),
            receiver=get_user_by_email(to),
            template=mail_data.template,
            data=dict(
                params=mail_params.__dict__,
                sender_str=str(sender),
                recivers_str=",".join(recivers)
            )
        )

        try:
            html = render_to_string(mail_data.template, mail_params.__dict__)

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
            print(str(e))
            _data = log.data
            _data['error'] = str(e)
            log.data = _data
        log.save()
