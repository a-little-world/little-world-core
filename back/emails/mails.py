from dataclasses import dataclass

"""
This file contains a dataclass for every email
This way we get typesafety for all emails,
and it is easy to tell which parameters are available
"""
# Pass


@dataclass
class WelcomeEmailParams:
    # We only talk to people in first name these days
    first_name: str
    second_name: str
    verification_code: str


# Register all templates and their serializers here
templates = [dict(
    name="welcome",
    template="emails/welcome.html",
    serializer=WelcomeEmailParams
)]


def get_mail_data_by_name(name):
    for t in templates:
        if t['name'] == name:
            return t
    # TODO: else thow some mail not found error
