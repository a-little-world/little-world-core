from dataclasses import dataclass
from rest_framework import serializers
from django.utils.translation import gettext as _

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
    second_name: str
    verification_code: str


# Register all templates and their serializers here
templates = [MailMeta(
    name="welcome",
    template="emails/welcome.html",
    params=WelcomeEmailParams
)]


def get_mail_data_by_name(name) -> MailMeta:
    for t in templates:
        if t.name == name:
            return t
    raise MailDataNotFoundErr(_("Mail data with name not found"))
