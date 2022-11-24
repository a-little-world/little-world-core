from dataclasses import dataclass
import string
from django.utils.translation import pgettext_lazy


class MissingEmailParamErr(Exception):
    pass


def inject_template_data(template_dict, params):
    """
    This takes one of the Templat Param classes below
    if this failes it means there is a missing parameter
    """
    _dict = template_dict.copy()
    # We need to take one of the templates from below
    # and for each parameter we check if there is a requred format string
    print(_dict)
    for k in _dict:
        # This allowes us to read all parameters
        _formats = list(string.Formatter().parse(str(_dict[k])))
        if not _formats:
            # If there is nothing to format,
            # e.g. on emty string, then skip this string
            continue
        _format_args = [arg for arg in list(string.Formatter().parse(str(_dict[k])))[
            0][1:] if arg != "" and arg is not None]
        print("Fomattable stuff ", _format_args)
        for _k in _format_args:
            if not _k in params:
                raise MissingEmailParamErr(
                    "Missing email template param: " + _k)

        _dict[k] = _dict[k].format(**{
            k: params[k] for k in _format_args
        })
        # print("Updated templte dict ", template_dict)
    return _dict


@dataclass
class WelcomeTemplateParamsDefaults:
    """
    This just works as a display of the default arguments
    """
    subject_header_text: str = 'SUBJECT_HEADER_TEXT'
    greeting: str = 'GREETING'
    content_start_text: str = 'CONTENT_START_TEXT'
    content_body_text: str = 'CONTENT_BODY_TEXT'
    link_box_text: str = 'LINK_BOX_TEXT'
    button_text: str = 'BUTTON_TEXT'
    button_link: str = 'BUTTON_LINK'
    below_link_text: str = 'BELOW_LINK_TEXT'
    footer_text: str = 'FOOTER_TEXT'
    goodbye: str = 'GOODBYE'
    goodbye_name: str = 'GOODBYE_NAME'


@dataclass
class WelcomeTemplateMail:
    """
    ---------------> WELCOME & E-mail Verification - mail <--------------------
    send on sighn-up to new user
    """
    subject_header_text: str = pgettext_lazy(
        "email.welcome.subject-header-text",
        "Willkommen bei Little World")
    greeting: str = pgettext_lazy(
        'email.welcome.greeting',
        'Hallo {first_name}')
    content_start_text: str = pgettext_lazy(
        'email.welcome.content-start-text',
        'Wir freuen uns, dass du dich bei Little World registriert hast!')
    content_body_text: str = pgettext_lazy(
        'email.welcome.content-body-text',
        'Damit wir wissen, dass deine E-Mail-Adresse wirklich dir gehört,' +
        'bestätige diese bitte mit einem Klick auf den Knopf unten, oder gib den Code: ')
    link_box_text: str = pgettext_lazy(
        'email.welcome.link-box-text',
        '{verification_code}')
    button_text: str = pgettext_lazy(
        'email.welcome.button-text',
        'E-Mail bestätigen')
    button_link: str = pgettext_lazy(
        'email.welcome.button-link',
        '{verification_url}')
    below_link_text: str = pgettext_lazy(
        'email.welcome.below-link-text',
        'auf unserer Website ein. ')
    footer_text: str = pgettext_lazy(
        'email.welcome.footer-text',
        'Solltest du dich nicht bei Little World registriert haben,'
        + ' kannst du diese E-Mail ignorieren.')
    goodbye: str = pgettext_lazy(
        'email.welcome.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.welcome.goodbye-name',
        'Dein Little World Team')


@dataclass
class MatchFoundEmailTexts:
    """
    ---------------> MATCH_FOUND_MAIL <--------------------
    """
    subject_header_text: str = pgettext_lazy(
        "email.match.subject-header-text",
        "Glückwunsch!" +
        "\nLerne jetzt {match_first_name} kennen")
    greeting: str = pgettext_lazy(
        'email.match.greeting',
        'Hallo {first_name}')
    content_start_text: str = pgettext_lazy(
        'email.match.content-start-text',
        'wir freuen uns, dir mitteilen zu können, dass wir ' +
        '{match_first_name} als Gesprächspartner:in für dich gefunden haben!')
    content_body_text: str = pgettext_lazy(
        'email.match.content-body-text',
        'Kontaktiere {match_first_name} einfach über Little World ' +
        'um ein erstes Gespräch zum Kennenlernen zu vereinbaren.')
    link_box_text: str = pgettext_lazy(
        'email.match.link-box-text',
        '')  # Emtpy -> means section auto removed in template rendering
    button_text: str = pgettext_lazy(
        'email.match.button-text',
        '{match_first_name} kennenlernen')
    button_link: str = pgettext_lazy(
        'email.match.button-link',
        '{profile_link_url}')
    below_link_text: str = pgettext_lazy(
        'email.match.below-link-text',
        '')
    footer_text: str = pgettext_lazy(
        'email.match.footer-text',
        'Eines unserer Teammitglieder kann euch dabei gerne begleiten.' +
        ' Schreib Oliver (Support) dafür einfach eine kurze Nachricht.')
    goodbye: str = pgettext_lazy(
        'email.match.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.match.goodbye-name',
        'Dein Little World Team')


@ dataclass
class PasswordResetEmailTexts:
    reset_subject: str = pgettext_lazy(
        'email.password-reset.reset-subject',
        ' Macht doch nichts! ')
    reset_body_start: str = pgettext_lazy(
        'email.password-reset.reset-body-start',
        'Hier kannst du dein Passwort zurück setzen')
    reset_button_text: str = pgettext_lazy(
        'email.password-reset.reset-button-text',
        'Passwort zurücksetzen')
    reset_button_url: str = pgettext_lazy(
        'email.password-reset.reset-button-url',
        '{password_reset_url}')


@ dataclass
class PasswordResetEmailDefaults:
    reset_subject: str = 'reset_subject'
    reset_body_start: str = 'reset_body_start'
    reset_button_text: str = 'reset_button_text'
    reset_button_url: str = 'reset_button_url'
