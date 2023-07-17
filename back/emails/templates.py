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
            if not (_k in params):
                raise MissingEmailParamErr(
                    "Missing email template param: " + _k + "GOt only" + str(params))

        if not isinstance(_dict[k], bool):
            # Only try to replace string values
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
class MatchRejectedEmailTexts:
    """
    Send if the user decided not to accept a match and wants to start looking for another match
    """
    subject_header_text: str = pgettext_lazy(
        "email.new-match-search.subject-header-text", "Neue Bekanntschaften suchen auf Little World")
    greeting: str = pgettext_lazy(
        'email.new-match-search.greeting',
        'Hallo {first_name}')
    content_start_text: str = pgettext_lazy(
        'email.new-match-search.content-start-text',
        'Du hast dich entschieden, deinen aktuellen Vorschlag nicht anzunehmen. Kein Problem! Es warten noch viele andere interessante Bekanntschaften auf dich. Melde dich einfach wieder bei Little World an und starte deine Suche nach neuen Bekanntschaften aus aller Welt.')
    content_body_text: str = pgettext_lazy(
        'email.new-match-search.content-body-text', '')
    link_box_text: str = pgettext_lazy(
        'email.new-match-search.link-box-text',
        '')  # Empty -> means section auto removed in template rendering
    button_text: str = pgettext_lazy(
        'email.new-match-search.button-text',
        'Neue Suche starten')
    button_link: str = pgettext_lazy(
        'email.new-match-search.button-link',
        'https://little-world.com/login/')
    below_link_text: str = pgettext_lazy(
        'email.new-match-search.below-link-text',
        '')
    footer_text: str = pgettext_lazy(
        'email.new-match-search.footer-text',
        '')
    goodbye: str = pgettext_lazy(
        'email.new-match-search.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.email.new-match-search.goodbye.goodbye-name',
        'Dein Little World Team')
    use_unsubscribe_footer: bool = True


@dataclass
class UnfinishedUserForm1Messages:
    """
    Send if the user registered and verified his email but did not finish the userform    
    send only one TODO
    """
    subject_header_text: str = pgettext_lazy(
        "email.unfinished-user-form-1.subject-header-text", "Umfrage beenden für Bekanntschaften aus aller Welt")
    greeting: str = pgettext_lazy(
        'email.unfinished-user-form-1.greeting',
        'Hallo {first_name}')
    content_start_text: str = pgettext_lazy(
        'email.unfinished-user-form-1.content-start-text',
        'nur fünf weitere Minuten trennen dich von neuen Bekanntschaften und interessanten Geschichten aus aller Welt. Beende jetzt deine Umfrage auf Little World. Dann kannst du kostenlos und flexibel mitmachen! Schon 30 Minuten pro Woche machen einen großen Unterschied.')
    content_body_text: str = pgettext_lazy(
        'email.unfinished-user-form-1.content-body-text', '')
    link_box_text: str = pgettext_lazy(
        'email.unfinished-user-form-1.link-box-text',
        '')  # Emtpy -> means section auto removed in template rendering
    button_text: str = pgettext_lazy(
        'email.unfinished-user-form-1.button-text',
        'Umfrage abschließen')
    button_link: str = pgettext_lazy(
        'email.unfinished-user-form-1.button-link',
        'https://little-world.com/form/')
    below_link_text: str = pgettext_lazy(
        'email.unfinished-user-form-1.below-link-text',
        '')
    footer_text: str = pgettext_lazy(
        'email.unfinished-user-form-1.footer-text',
        '')
    goodbye: str = pgettext_lazy(
        'email.unfinished-user-form-1.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.email.unfinished-user-form-1.goodbye.goodbye-name',
        'Dein Little World Team')
    use_unsubscribe_footer: bool = True


@dataclass
class UnfinishedUserForm2Messages:
    """
    Follow up email about the unfinished userform
    """
    subject_header_text: str = pgettext_lazy(
        "email.unfinished-user-form-2.subject-header-text", "Mit 30 Minuten helfen - Umfrage beenden")
    greeting: str = pgettext_lazy(
        'email.unfinished-user-form-2.greeting',
        'Hallo {first_name}')
    content_start_text: str = pgettext_lazy(
        'email.unfinished-user-form-2.content-start-text',
        'Dein Engagement zählt! Willst du Teil der Gemeinschaft von Little World werden und tolle Menschen aus aller Welt kennenlernen? Beende dafür in nur 5 Minuten unsere Umfrage:')
    content_body_text: str = pgettext_lazy(
        'email.unfinished-user-form-2.content-body-text', '')
    link_box_text: str = pgettext_lazy(
        'email.unfinished-user-form-2.link-box-text',
        '')  # Emtpy -> means section auto removed in template rendering
    button_text: str = pgettext_lazy(
        'email.unfinished-user-form-2.button-text',
        'Umfrage abschließen')
    button_link: str = pgettext_lazy(
        'email.unfinished-user-form-2.button-link',
        'https://little-world.com/form/')
    below_link_text: str = pgettext_lazy(
        'email.unfinished-user-form-2.below-link-text',
        '')
    footer_text: str = pgettext_lazy(
        'email.unfinished-user-form-2.footer-text',
        'Du hast Fragen? Wir sind für dich da! Ruf an unter {team_phone} oder schreib uns unter {team_email}. Wir helfen dir gerne')
    goodbye: str = pgettext_lazy(
        'email.unfinished-user-form-2.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.email.unfinished-user-form-2.goodbye.goodbye-name',
        'Dein Little World Team')
    use_unsubscribe_footer: bool = True
    
@dataclass
class StillInContactMessages:
    """
    Send to ask users if they are still in contact with their match
    """
    subject_header_text: str = pgettext_lazy(
        "email.still-in-contact.subject-header-text", "Noch in Kontakt mit {match_name}?")
    greeting: str = pgettext_lazy(
        'email.still-in-contact.greeting',
        'Hallo {first_name},')
    content_start_text: str = pgettext_lazy(
        'email.still-in-contact.content-start-text',
        'wie geht es dir und {match_name}? Wir hoffen, eure Gespräche bereiten euch weiterhin viel Freude. Bitte gib uns eine kurze Rückmeldung für unsere Wirkungsmessung: Unterhältst du dich noch mit {match_name}?')
    content_body_text: str = pgettext_lazy(
        'email.still-in-contact.content-body-text', '')
    link_box_text: str = pgettext_lazy(
        'email.still-in-contact.link-box-text',
        '')  # Empty -> means section auto removed in template rendering
    button_text: str = pgettext_lazy(
        'email.still-in-contact.button-text',
        'Ja')
    button_link: str = pgettext_lazy(
        'email.still-in-contact.button-link',
        'https://little-world.com/contact-yes/')
    button_text_alt: str = pgettext_lazy(
        'email.still-in-contact.button-text-alt',
        'Nein')
    button_link_alt: str = pgettext_lazy(
        'email.still-in-contact.button-link-alt',
        'https://little-world.com/contact-no/')
    below_link_text: str = pgettext_lazy(
        'email.still-in-contact.below-link-text',
        '')
    footer_text: str = pgettext_lazy(
        'email.still-in-contact.footer-text',
        '')
    goodbye: str = pgettext_lazy(
        'email.still-in-contact.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.still-in-contact.goodbye.goodbye-name',
        'Dein Little World Team')
    use_unsubscribe_footer: bool = True
    
@dataclass
class EmailVerificationReminderMessages:
    """
    Send if the user registered but did not verify their email yet
    """
    subject_header_text: str = pgettext_lazy(
        "email.email-verification-reminder.subject-header-text", "Bitte bestätige deine E-Mail-Adresse für Little World")
    greeting: str = pgettext_lazy(
        'email.email-verification-reminder.greeting',
        'Hallo {first_name}')
    content_start_text: str = pgettext_lazy(
        'email.email-verification-reminder.content-start-text',
        'du hast dich kürzlich bei Little World registriert, aber deine E-Mail-Adresse noch nicht bestätigt. Um alle Funktionen unserer Plattform nutzen zu können und mit Menschen aus aller Welt in Kontakt zu treten, bitten wir dich, deine E-Mail-Adresse zu bestätigen.')
    content_body_text: str = pgettext_lazy(
        'email.email-verification-reminder.content-body-text', '')
    link_box_text: str = pgettext_lazy(
        'email.email-verification-reminder.link-box-text',
        '')  # Empty -> means section auto removed in template rendering
    button_text: str = pgettext_lazy(
        'email.email-verification-reminder.button-text',
        'E-Mail-Adresse bestätigen')
    button_link: str = pgettext_lazy(
        'email.email-verification-reminder.button-link',
        'https://little-world.com/verify-email/')
    below_link_text: str = pgettext_lazy(
        'email.email-verification-reminder.below-link-text',
        '')
    footer_text: str = pgettext_lazy(
        'email.email-verification-reminder.footer-text',
        '')
    goodbye: str = pgettext_lazy(
        'email.email-verification-reminder.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.email-verification-reminder.goodbye.goodbye-name',
        'Dein Little World Team')
    use_unsubscribe_footer: bool = True


@dataclass
class ConfirmMatchMail1Texts:
    """
    Follow up email about the unfinished userform
    """
    subject_header_text: str = pgettext_lazy(
        "email.confirm-match-1.subject-header-text", "Match gefunden - jetzt bestätigen")
    greeting: str = pgettext_lazy(
        'email.confirm-match-1.greeting',
        'Hallo {first_name}')
    content_start_text: str = pgettext_lazy(
        'email.confirm-match-1.content-start-text',
        '{match_first_name} freut sich schon darauf, dich kennenzulernen! Ihr scheint auch schon eine Menge gemeinsam zu haben. Was das ist, erfährst Du hier:')
    content_body_text: str = pgettext_lazy(
        'email.confirm-match-1.content-body-text', '')
    link_box_text: str = pgettext_lazy(
        'email.confirm-match-1.link-box-text',
        '')  # Emtpy -> means section auto removed in template rendering
    button_text: str = pgettext_lazy(
        'email.confirm-match-1.button-text',
        'Jetzt match bestätigen')
    button_link: str = pgettext_lazy(
        'email.confirm-match-1.button-link',
        'https://little-world.com/app/')  # TODO: this would be supposed to render a match confirm page instead of a general app page
    below_link_text: str = pgettext_lazy(
        'email.confirm-match-1.below-link-text',
        '')
    footer_text: str = pgettext_lazy(
        'email.confirm-match-1.footer-text',
        'Dort kannst du auch den Gesprächsvorschlag mit MATCH_NAME annehmen. \n' +
        'Du hast Fragen? Wir sind für dich da! Ruf an unter {team_phone} oder schreib uns unter {team_email}. Wir helfen dir gerne')
    goodbye: str = pgettext_lazy(
        'email.confirm-match-1.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.email.confirm-match-1.goodbye.goodbye-name',
        'Dein Little World Team')
    use_unsubscribe_footer: bool = True


@dataclass
class ConfirmMatchMail2Texts:
    """
    Email to ask user to confirm his match
    """
    subject_header_text: str = pgettext_lazy(
        "email.confirm-match-2.subject-header-text", "Dein match wartet - höchste Zeit zu bestätigen")
    greeting: str = pgettext_lazy(
        'email.confirm-match-2.greeting',
        'Hallo {first_name}')
    content_start_text: str = pgettext_lazy(
        'email.confirm-match-2.content-start-text',
        'du hattest vor Kurzem eine Übereinstimmung auf der Plattform Little World. Gerne würde sich {match_first_name} mit dir unterhalten! Um ihn/sie allerdings nicht zu lange warten zu lassen, werden wir {match_first_name} weitervermitteln, sollten wir nichts von dir hören.\n' +
        'Du möchtest mehr über {match_first_name} erfahren? Dann klicke hier: ')
    content_body_text: str = pgettext_lazy(
        'email.confirm-match-2.content-body-text', '')
    link_box_text: str = pgettext_lazy(
        'email.confirm-match-2.link-box-text',
        '')  # Emtpy -> means section auto removed in template rendering
    button_text: str = pgettext_lazy(
        'email.confirm-match-2.button-text',
        'Mehr Info')
    button_link: str = pgettext_lazy(
        'email.confirm-match-2.button-link',
        'https://little-world.com/app/')  # TODO: this would be supposed to render a match confirm page instead of a general app page
    below_link_text: str = pgettext_lazy(
        'email.confirm-match-2.below-link-text',
        '')
    footer_text: str = pgettext_lazy(
        'email.confirm-match-2.footer-text',
        'Dort kannst du auch den Gesprächsvorschlag mit {match_first_name} annehmen. \n' +
        'Du hast Fragen? Wir sind für dich da! Ruf an unter {team_phone} oder schreib uns unter {team_email}. Wir helfen dir gerne')
    goodbye: str = pgettext_lazy(
        'email.confirm-match-2.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.email.confirm-match-2.goodbye.goodbye-name',
        'Dein Little World Team')
    use_unsubscribe_footer: bool = True
    
@dataclass
class MatchExpiredMailTexts:
    """
    Email to inform user that their match has expired
    """
    subject_header_text: str = pgettext_lazy(
        "email.match-expired.subject-header-text", "Dein Match ist abgelaufen - Finde einen neuen Partner")
    greeting: str = pgettext_lazy(
        'email.match-expired.greeting',
        'Hallo {first_name}')
    content_start_text: str = pgettext_lazy(
        'email.match-expired.content-start-text',
        'leider ist die Zeit abgelaufen, um {match_first_name} auf der Plattform Little World zu bestätigen. Aber keine Sorge, du kannst dich einloggen und nach einem neuen Match suchen.\n' +
        'Möchtest du jetzt nach einem neuen Match suchen? Dann klicke hier: ')
    content_body_text: str = pgettext_lazy(
        'email.match-expired.content-body-text', '')
    link_box_text: str = pgettext_lazy(
        'email.match-expired.link-box-text',
        '')  # Empty -> means section auto removed in template rendering
    button_text: str = pgettext_lazy(
        'email.match-expired.button-text',
        'Neues Match finden')
    button_link: str = pgettext_lazy(
        'email.match-expired.button-link',
        'https://little-world.com/app/')  # TODO: this would be supposed to render a match search page instead of a general app page
    below_link_text: str = pgettext_lazy(
        'email.match-expired.below-link-text',
        '')
    footer_text: str = pgettext_lazy(
        'email.match-expired.footer-text',
        'Du hast Fragen? Wir sind für dich da! Ruf an unter {team_phone} oder schreib uns unter {team_email}. Wir helfen dir gerne')
    goodbye: str = pgettext_lazy(
        'email.match-expired.goodbye',
        'Beste Grüße,')
    goodbye_name: str = pgettext_lazy(
        'email.match-expired.goodbye.goodbye-name',
        'Dein Little World Team')
    use_unsubscribe_footer: bool = True

@dataclass
class InterviewInvitation:
    """
    ---------> Interview invitation email <---------------
    """
    subject_header_text: str = pgettext_lazy(
        "email.interview-invitation.subject-header-text", "Einladung zum Online-Interview mit Aniqa")
    greeting: str = pgettext_lazy(
        'email.interview-invitation.greeting',
        'Hallo {first_name}!')
    content_start_text: str = pgettext_lazy(
        'email.interview-invitation.content-start-text',
        'Mein Name ist Aniqa und ich bin derzeit Studentin an der Universität Siegen im Bereich'
        ' Human Computer Interaction. Im Rahmen meiner Projektarbeit mit Little World führe ich'
        ' Online-Interviews mit (englischsprachigen) Ehrenamtlichen durch, um die'
        ' Nutzererfahrungen mit Little World besser zu verstehen.')
    content_body_text: str = pgettext_lazy(
        'email.interview-invitation.content-body-text',
        mark_safe('Wenn du helfen möchtest die Plattform für andere Benutzer*innen zu verbessern oder'
        ' einfach eine nette Studentin in ihrer Projektarbeit unterstützen möchtest, dann melde'
        ' dich bitte bei mir. Nimm gerne einen Kaffee oder Tee zum Online-Interview mit, es wird'
        ' alles ganz entspannt und dauert nicht mehr als eine Stunde. Ich freue mich auf einen'
        ' lebhaften Ideenaustausch mit dir!<br></br>'
        'Hier ist meine E-Mail-Adresse: '))
    link_box_text: str = mark_safe('<a href="mailto:aniqa.rahman@student.uni-siegen.de?subject=Interview" style="color: blue;">aniqa.rahman@student.uni-siegen.de</a>')
    button_text: str = pgettext_lazy(
        'email.interview-invitation.button-text',
        'Interview-Termin buchen')
    button_link: str = pgettext_lazy(
        'email.interview-invitation.button-link',
        '{link_url}')
    below_link_text: str = pgettext_lazy(
        'email.interview-invitation.below-link-text',
        'Thank you so much for your time,')
    footer_text: str = pgettext_lazy(
        'email.interview-invitation.footer-text',
        'PS: das Team von Little World hat diese E-Mail im Namen von Aniqa an dich'
        ' weitergeleitet. Solltest du in Zukunft keine Interview-Bitten mehr erhalten wollen, so'
        ' klicke bitte auf E-Mail Abmelden.')
    goodbye: str = pgettext_lazy(
        'email.interview-invitation.goodbye',
        'Aniqa Rahman')
    goodbye_name: str = pgettext_lazy(
        'email.email.interview-invitation.goodbye.goodbye-name',
        '')
    use_unsubscribe_footer:bool=True
    unsubscribe_two_link:bool = False
    unsubscribe_link1: str = '{unsubscribe_url1}'
    unsubscribe_link1_category: str = 'special interview request'
    unsubscribe_link2: str = 'none'
    unsubscribe_link2_category: str = 'none'
    
@dataclass
class SurveyInvitationAniq2:
    """
    ---------> Survey invitation email <---------------
    """
    subject_header_text: str = pgettext_lazy(
        "email.survey-invitation.subject-header-text", "Studentin bittet um Unterstützung – Umfrage bei Little World")
    greeting: str = pgettext_lazy(
        'email.survey-invitation.greeting',
        'Hallo {first_name},')
    content_start_text: str = pgettext_lazy(
        'email.survey-invitation.content-start-text','Möchtest du uns helfen unsere Little World Plattform zu verbessern oder Aniqa bei ihrer Projektarbeit?')
    link_box_text: str = mark_safe('<a href="https://s.surveyplanet.com/iuhajmj7" style="color: blue;">https://s.surveyplanet.com/iuhajmj7</a>')
    content_body_text: str = pgettext_lazy(
        'email.survey-invitation.content-body-text',
        ' Dann lade ich dich herzlich ein, an der 10-15-minütigen Umfrage von der Studentin Aniqa teilzunehmen unter ')
    button_text: str = pgettext_lazy(
        'email.survey-invitation.button-text',
        'Zur Umfrage')
    button_link: str = pgettext_lazy(
        'email.survey-invitation.button-link',
        '{link_url}')
    below_link_text: str = pgettext_lazy(
        'email.survey-invitation.below-link-text',
        mark_safe(
            'Dein wertvolles Feedback wird uns dabei helfen, die notwendigen Änderungen oder Erweiterungen an'
            ' unserem Angebot vorzunehmen. Diese Umfrage ist völlig anonym und vertraulich, also teile uns bitte'
            ' deine ehrlichen Gedanken und Meinungen mit.<br></br>Aniqa ist eine Studentin der Universität Siegen,'
            ' die derzeit eine Projektarbeit bei uns schreibt. Wenn du Fragen oder Bedenken hast, wende dich gerne'
            ' jederzeit an uns.'
            '<br></br>Vielen Dank im Voraus für deine Unterstützung!'))
    footer_text: str = pgettext_lazy(
        'email.survey-invitation.footer-text',
        'Herzliche Grüße,')
    goodbye: str = pgettext_lazy(
        'email.survey-invitation.goodbye',
        mark_safe('Das Little World Team<br></br>'))
    goodbye_name: str = pgettext_lazy(
        'email.survey-invitation.goodbye-name',
        '')
    use_unsubscribe_footer:bool=True
    unsubscribe_two_link:bool = False
    unsubscribe_link1: str = '{unsubscribe_url1}'
    unsubscribe_link1_category: str = 'survey request'
    unsubscribe_link2: str = 'none'
    unsubscribe_link2_category: str = 'none'

@dataclass
class GeneralSurveyMail:
    """
    ---------> Survey email <---------------
    """
    subject_header_text: str = pgettext_lazy(
        "email.survey.subject-header-text", "Umfrage zur Verbesserung von Little World")
    greeting: str = pgettext_lazy(
        'email.survey.greeting',
        'Hallo {first_name},')
    content_start_text: str = mark_safe(pgettext_lazy(
        'email.survey.content-start-text',
        'wir möchten Little World für dich und andere Mitglieder weiter verbessern. Du kannst uns dabei helfen, indem du unsere kurze 3-minütige Umfrage ausfüllst und uns mitteilst, welche Gruppenangebote du dir noch wünschst.'
        'Auf die Ergebnisse musst du aber nicht warten. Schon jetzt kannst du dich jeden Dienstag ab 18 Uhr austauschen oder einfach nur zuhören – unverbindlich und in einer kleinen Gruppe. Die beliebtesten Angebote aus unserer Umfrage kommen dann Schritt für Schritt hinzu.'))
    button_text: str = pgettext_lazy(
        'email.survey.button-text',
        'ZUR UMFRAGE (google form)')
    button_link: str = pgettext_lazy(
        'email.survey.button-link',
        '{link_url}')
    content_body_text: str = mark_safe(pgettext_lazy(
        'email.survey.content-body-text',
        '<br></br>Den Austausch am Dienstag findest du nach dem Einloggen unter "Start" und dann unter "Kaffeeklatsch" oder einfach über folgenden Link:'))
    link_box_text: str = mark_safe(pgettext_lazy(
        'email.survey.link-box-text',
        '<a href="https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09" style="color: blue;">https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09</a>'))
    below_link_text: str = mark_safe(pgettext_lazy(
        'email.survey.below-link-text',
        ''))
    footer_text: str = pgettext_lazy(
        'email.survey.footer-text',
        'Du hast noch Fragen? Melde dich gerne jederzeit - unsere Kontaktdaten findest du in der Signatur. Wir helfen dir gerne weiter.')
    goodbye: str = pgettext_lazy(
        'email.survey.goodbye',
        'Dein Team von Little World')
    goodbye_name: str = pgettext_lazy(
        'email.email.survey.goodbye.goodbye-name',
        '')
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = '{unsubscribe_url1}'
    unsubscribe_link1_category: str = 'Von Umfrage E-Mails abmelden'
    unsubscribe_link2: str = 'none'
    unsubscribe_link2_category: str = 'none'


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
