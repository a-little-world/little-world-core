from dataclasses import dataclass
import string
from django.utils.translation import pgettext_lazy
from django.utils.safestring import mark_safe


class MissingEmailParamErr(Exception):
    pass


def inject_template_data(template_dict, params):
    """
    This takes one of the Templat Param classes below
    if this failes it means there is a missing parameter
    """
    #print(template_dict, params)
    _dict = template_dict.copy()
    # We need to take one of the templates from below
    # and for each parameter we check if there is a requred format string
    for k in _dict:
        # This allowes us to read all parameters
        _formats = list(string.Formatter().parse(str(_dict[k])))
        if not _formats:
            # If there is nothing to format,
            # e.g. on emty string, then skip this string
            continue
        _format_args = [arg for arg in list(string.Formatter().parse(str(_dict[k])))[
            0][1:] if arg != "" and arg is not None]
        #print("Fomattable stuff ", _format_args)
        for _k in _format_args:
            if not _k in params:
                raise MissingEmailParamErr(
                    "Missing email template param: " + _k)

        _dict[k] = _dict[k].format(**{
            k: params[k] for k in _format_args
        })
        #print("Updated templte dict ", _dict)
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
class RAWTemplateMail:
    subject_header_text: str = '{subject_header_text}'
    greeting: str = '{greeting}'
    content_start_text: str = '{content_start_text}'
    content_body_text: str = '{content_body_text}'
    link_box_text: str = '{link_box_text}'
    button_text: str = '{button_text}'
    button_link: str = '{button_link}'
    below_link_text: str = '{below_link_text}'
    footer_text: str = '{footer_text}'
    goodbye: str = '{goodbye}'
    goodbye_name: str = '{goodbye_name}'


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


@dataclass
class NewUnreadMessages:
    """
    ---------------> Unread messages mail <--------------------
    """
    subject_header_text: str = pgettext_lazy(
        "email.new-unread-messages.subject-header-text", "Neue Nachrichten")
    greeting: str = pgettext_lazy(
        'email.new-unread-messages.greeting',
        'Hallo {first_name}')
    content_start_text: str = pgettext_lazy(
        'email.new-unread-messages.content-start-text',
        'Du hast neue Nachricht(en) auf Little World erhalten. Du kannst deine Nachrichten in dem Chat von Little World ansehen, indem du auf folgenden Knopf drückst:')
    content_body_text: str = pgettext_lazy(
        'email.new-unread-messages.content-body-text', '')
    link_box_text: str = pgettext_lazy(
        'email.new-unread-messages.link-box-text',
        '')  # Emtpy -> means section auto removed in template rendering
    button_text: str = pgettext_lazy(
        'email.new-unread-messages.button-text',
        'Neue Nachrichten anzeigen')
    button_link: str = pgettext_lazy(
        'email.new-unread-messages.button-link',
        'https://little-world.com/app/chat')
    below_link_text: str = pgettext_lazy(
        'email.new-unread-messages.below-link-text',
        '')
    footer_text: str = pgettext_lazy(
        'email.new-unread-messages.footer-text',
        '')
    goodbye: str = pgettext_lazy(
        'email.new-unread-messages.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.email.new-unread-messages.goodbye.goodbye-name',
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


@dataclass
class SorryWeStillNeedALittleMail:
    subject_header_text: str = 'Suche & Gruppengespräche'
    greeting: str = 'Hi {first_name}'
    content_start_text: str = mark_safe(
        'wow, hunderte von Menschen haben sich in den letzten Wochen für die ' +
        '<i>Beta-Version</i> von <b>Little World</b> registriert. Vielen Dank euch!')
    content_body_text: str = mark_safe(
        'Unser kleines Team arbeitet auf Hochtouren daran, ' +
        'für alle die passenden Gesprächspartner:innen zu finden –' +
        ' das schaffen wir noch nicht überall auf Anhieb. ' +
        'Dafür möchten wir uns entschuldigen, dafür bieten wir aber auch eine Lösung an.' + '<br><br>' +
        'Unser Vorschlag: Um schneller zu matchen, erhöhen wir ab <b>Sonntag, 27. November 2022</b>, ' +
        'den Suchradius auf 100 km. Alle deine anderen Einstellungen bleiben genauso, wie sie waren. ' +
        'Solltest du aber weiterhin bei „möglichst in der Nähe“ bleiben wollen, ist das auch kein Problem. ' +
        'Dann antworte ganz einfach auf diese Mail, am besten mit einer maximalen Entfernung.' + '<br><br>' +
        'Hast du noch Fragen? Dann melde dich jederzeit unter <i>0152 34 777 471</i> oder <i>oliver.berlin@little-world.com</i> oder über den Chat auf unserer Webseite. <br>' +
        'Oder besuche unsere <b>Gruppengespräche</b> für Fragen & Anregungen. ' +
        'Diese findest ab jetzt immer angemeldet auf <a href="www.little-world.com">www.little-world.com</a> unter dem Bereich „Start“ und dann „Kaffeeklatsch“ zu wechselnden Zeiten. ' +
        ' Als nächstes treffen wir uns <b>dienstags 18 - 19 Uhr</b> und <b>donnerstags 13 - 14 Uhr</b>.')
    link_box_text: str = ''
    button_text: str = ''
    button_link: str = ''
    below_link_text: str = ''
    footer_text: str = ''
    goodbye: str = 'Wir freuen uns über jeden Austausch,'
    goodbye_name: str = 'dein Team von Little World'


@dataclass
class NewServerMail:
    subject_header_text: str = 'Serverumzug & Neuigkeiten'
    greeting: str = 'Liebe Community,'
    content_start_text: str = mark_safe(
        'wir sind umgezogen – es ging auf einen neuen Server. Sorry, sollte es weiterhin zu technischen Problemen kommen. Meldet euch bitte bei unserem Support und wir kümmern uns umgehend darum!'
        + ' Dieser Schritt war wichtig: für mehr Nutzer:innen, einen schnelleren Matching-Prozess und weitere Features und Verbesserungen, auf die ihr euch bald freuen könnt!')
    content_body_text: str = mark_safe('Wir freuen uns über <b>750 Anmeldungen</b>! Vielen Dank für eure Hilfe, euer Engagement, euer Vertrauen und all die Verbesserungsvorschläge! Unser kleines Team arbeitet auf Hochtouren daran, alles umzusetzen und für alle ein Match zu finden – das schaffen wir noch nicht überall auf Anhieb. Dafür möchten wir uns entschuldigen, dafür bieten wir aber auch eine Lösung an:'
                                       + '<br><br>' + 'Erzählt anderen Leuten von Little World; folgt uns auf <b>Social Media</b>, teilt unsere Beiträge und helft uns dabei, dass Little World weiter wächst! Denn auch jetzt warten noch mehr als 120 Deutschlernende auf ein Match. Je mehr Leute von uns wissen, desto schneller finden wir für alle Gesprächspartner:innen.')
    social_banner_header_text: str = 'Ihr findet uns auf folgenden Plattformen:'
    link_box_text: str = ''
    button_text: str = ''
    button_link: str = ''
    below_link_text: str = ''
    footer_text: str = ''
    goodbye: str = 'Vielen Dank für eure Unterstützung!'
    goodbye_name: str = 'Das gesamte Team von Little World wünscht euch frohe Feiertage und einen guten Rutsch ins neue Jahr!'
