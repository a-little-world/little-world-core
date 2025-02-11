import string
from dataclasses import dataclass

from django.utils.safestring import mark_safe


class MissingEmailParamErr(Exception):
    pass


def inject_template_data(template_dict, params):
    """
    This takes one of the Templat Param classes below
    if this failes it means there is a missing parameter
    """
    _dict = template_dict.copy()
    for k in _dict:
        _formats = list(string.Formatter().parse(str(_dict[k])))
        if not _formats:
            continue
        _format_args = [
            arg for arg in list(string.Formatter().parse(str(_dict[k])))[0][1:] if arg != "" and arg is not None
        ]
        for _k in _format_args:
            if _k not in params:
                raise MissingEmailParamErr("Missing email template param: " + _k + "GOt only" + str(params))

        if not isinstance(_dict[k], bool):
            _dict[k] = _dict[k].format(**{k: params[k] for k in _format_args})
    return _dict


@dataclass
class WelcomeTemplateParamsDefaults:
    subject_header_text: str = "SUBJECT_HEADER_TEXT"
    greeting: str = "GREETING"
    content_start_text: str = "CONTENT_START_TEXT"
    content_body_text: str = "CONTENT_BODY_TEXT"
    link_box_text: str = "LINK_BOX_TEXT"
    button_text: str = "BUTTON_TEXT"
    button_link: str = "BUTTON_LINK"
    below_link_text: str = "BELOW_LINK_TEXT"
    footer_text: str = "FOOTER_TEXT"
    goodbye: str = "GOODBYE"
    goodbye_name: str = "GOODBYE_NAME"


@dataclass
class RAWTemplateMail:
    subject_header_text: str = "{subject_header_text}"
    greeting: str = "{greeting}"
    content_start_text: str = "{content_start_text}"
    content_body_text: str = "{content_body_text}"
    link_box_text: str = "{link_box_text}"
    button_text: str = "{button_text}"
    button_link: str = "{button_link}"
    below_link_text: str = "{below_link_text}"
    footer_text: str = "{footer_text}"
    goodbye: str = "{goodbye}"
    goodbye_name: str = "{goodbye_name}"


@dataclass
class WelcomeTemplateMail:
    subject_header_text: str = "Willkommen bei Little World"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = "Wir freuen uns, dass du dich bei Little World registriert hast!"
    content_body_text: str = "Damit wir wissen, dass deine E-Mail-Adresse wirklich dir gehört, bestätige diese bitte mit einem Klick auf den Knopf unten, oder gib den Code: "
    link_box_text: str = "{verification_code}"
    button_text: str = "E-Mail bestätigen"
    button_link: str = "{verification_url}"
    below_link_text: str = "auf unserer Website ein."
    footer_text: str = "Solltest du dich nicht bei Little World registriert haben, kannst du diese E-Mail ignorieren."
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"


@dataclass
class MatchFoundEmailTexts:
    subject_header_text: str = "Glückwunsch!\nLerne jetzt {match_first_name} kennen"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = "wir freuen uns, dir mitteilen zu können, dass wir {match_first_name} als Gesprächspartner:in für dich gefunden haben!"
    content_body_text: str = "Kontaktiere {match_first_name} einfach über Little World um ein erstes Gespräch zum Kennenlernen zu vereinbaren."
    link_box_text: str = ""
    button_text: str = "{match_first_name} kennenlernen"
    button_link: str = "{profile_link_url}"
    below_link_text: str = ""
    footer_text: str = "Eines unserer Teammitglieder kann euch dabei gerne begleiten. Schreib Oliver (Support) dafür einfach eine kurze Nachricht."
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"


@dataclass
class AccountDeletedEmailTexts:
    subject_header_text: str = "Account erfolgreich gelöscht"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = "Wir möchten dich darüber informieren, dass dein Account erfolgreich gelöscht wurde."
    content_body_text: str = "Bitte beachte, dass diese Aktion nicht rückgängig gemacht werden kann und alle deine verbleibenden Benutzerdaten dauerhaft gelöscht wurden."
    link_box_text: str = ""
    button_text: str = "Neuen Account erstellen"
    button_link: str = "{registration_link_url}"
    below_link_text: str = "Falls du dich entscheidest, einen neuen Account zu registrieren, beachte bitte, dass du einen neuen Account von Grund auf erstellen musst."
    footer_text: str = "Bei Fragen oder Anliegen wende dich bitte an unser Support-Team."
    goodbye: str = "Viele Grüße,"
    goodbye_name: str = "Dein Little World Team"


@dataclass
class MatchRejectedEmailTexts:
    subject_header_text: str = "Neue Bekanntschaften suchen auf Little World"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = "Du hast dich entschieden, deinen aktuellen Vorschlag nicht anzunehmen. Kein Problem! Es warten noch viele andere interessante Bekanntschaften auf dich. Melde dich einfach wieder bei Little World an und starte deine Suche nach neuen Bekanntschaften aus aller Welt."
    content_body_text: str = ""
    link_box_text: str = ""
    button_text: str = "Neue Suche starten"
    button_link: str = "https://little-world.com/login/"
    below_link_text: str = ""
    footer_text: str = ""
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"
    use_unsubscribe_footer: bool = True


@dataclass
class UserSurveyInvitationEmailNatalia:
    subject_header_text: str = "Einladung zu einem Online-Interview mit Natalia"
    greeting: str = "Hallo {first_name}!"
    content_start_text: str = "Mein Name ist Natalia und ich bin derzeit Studentin an der Universität Siegen im Bereich Human Computer Interaction. Im Rahmen meiner Projektarbeit mit Little World führe ich Online-Interviews (auf Englisch) durch. Das Thema der Interviews ist deine Motivation zur Teilnahme auf und Erweiterungen von Little World."
    content_body_text: str = "Wenn du helfen möchtest die Plattform für andere Benutzer:innen zu verbessern oder du mich einfach in meiner Projektarbeit unterstützen möchtest, dann melde dich bitte bei mir. Nimm gerne einen Kaffee oder Tee zum Online-Interview mit, es wird alles ganz entspannt und dauert 60-80 Minuten. Ich freue mich auf einen lebhaften Ideenaustausch mit dir! Bitte hilf mir in der Projektarbeit und schreibe mir unter:"
    link_box_text: str = mark_safe(
        '<a href="mailto:natalia.romancheva@student.uni-siegen.de?subject=Interview" style="color: blue;">natalia.romancheva@student.uni-siegen.de</a>'
    )
    button_text: str = "Natalia helfen (E-Mail)"
    button_link: str = "mailto:natalia.romancheva@student.uni-siegen.de"
    below_link_text: str = "PS: das Team von Little World hat diese E-Mail im Namen von Natalia an dich weitergeleitet. Solltest du in Zukunft keine Interview-Bitten mehr erhalten wollen, so klicke bitte auf E-Mail Abmelden."
    footer_text: str = ""
    goodbye: str = ""
    goodbye_name: str = "Natalia Romancheva"
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "survey request"


@dataclass
class UserInterviewRequestEmail:
    subject_header_text: str = "Interviewanfrage für ein Universitätsprojekt"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = "Unsere zwei Studentinnen Natalia und Sandra suchen noch 5 weitere Ehrenamtliche für ein Interview. Hast du zwischen 30 und 60 Minuten Zeit, ihnen zu helfen?"
    content_body_text: str = mark_safe(
        'Die Erreichbarkeiten sind: \
        <ul>\
        <li>Sandra unter \
        <a href="mailto:sandra.butzek@student.uni-siegen.de" style="color: blue;">sandra.butzek@student.uni-siegen.de</a></li> \
        <li>Natalia unter <a href="mailto:natalia.romancheva@student.uni-siegen.de" style="color: blue;">natalia.romancheva@student.uni-siegen.de</a></li>\
        </ul>\
        Die Themen sind unser zukünftiges Matching sowie zusätzliche Dank- und Belohnungssysteme. \
        Deine Antworten helfen den Studentinnen, ihr an der Uni gelerntes Wissen praktisch anzuwenden \
        und dem Team von Little World, bessere Entscheidungen für die zukünftige Weiterentwicklung von Little World zu treffen. \
        Für deine Hilfe wären wir dir sehr dankbar. \
        Deine Daten und Antworten werden nicht veröffentlicht. Du kannst auch teilnehmen, wenn du neu bei Little World bist oder \
        früher einmal dabei warst.'
    )
    link_box_text: str = ""
    button_text: str = "E-Mail an Sandra und Natalia senden"
    button_link: str = "mailto:sandra.butzek@student.uni-siegen.de;natalia.romancheva@student.uni-siegen.de"
    below_link_text: str = ""
    footer_text: str = ""
    goodbye: str = "Sommerliche Grüße"
    goodbye_name: str = "Oliver vom Team Little World"
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "interview request"


@dataclass
class UnfinishedUserForm1Messages:
    subject_header_text: str = "Umfrage beenden für Bekanntschaften aus aller Welt"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = "nur fünf weitere Minuten trennen dich von neuen Bekanntschaften und interessanten Geschichten aus aller Welt. Beende jetzt deine Umfrage auf Little World. Dann kannst du kostenlos und flexibel mitmachen! Schon 30 Minuten pro Woche machen einen großen Unterschied."
    content_body_text: str = ""
    link_box_text: str = ""
    button_text: str = "Umfrage abschließen"
    button_link: str = "https://little-world.com/form/"
    below_link_text: str = ""
    footer_text: str = ""
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "finish reminders"


@dataclass
class UnfinishedUserForm2Messages:
    subject_header_text: str = "Mit 30 Minuten helfen - Umfrage beenden"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = "Dein Engagement zählt! Willst du Teil der Gemeinschaft von Little World werden und tolle Menschen aus aller Welt kennenlernen? Beende dafür in nur 5 Minuten unsere Umfrage:"
    content_body_text: str = ""
    link_box_text: str = ""
    button_text: str = "Umfrage abschließen"
    button_link: str = "https://little-world.com/form/"
    below_link_text: str = ""
    footer_text: str = "Du hast Fragen? Wir sind für dich da! Ruf an unter {team_phone} oder schreib uns unter {team_email}. Wir helfen dir gerne"
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "finish reminders"


@dataclass
class StillInContactMessages:
    subject_header_text: str = "Noch in Kontakt mit {partner_first_name}?"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = "wie geht es dir und {partner_first_name}? Wir hoffen, eure Gespräche bereiten euch weiterhin viel Freude. Bitte gib uns eine kurze Rückmeldung für unsere Wirkungsmessung: Unterhältst du dich noch mit {partner_first_name}?"
    content_body_text: str = ""
    link_box_text: str = ""
    button_text: str = "Ja"
    button_link: str = "https://little-world.com/contact-yes/"
    button_text_alt: str = "Nein"
    button_link_alt: str = "https://little-world.com/contact-no/"
    below_link_text: str = ""
    footer_text: str = ""
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"
    use_unsubscribe_footer: bool = True


@dataclass
class EmailVerificationReminderMessages:
    """
    Send if the user registered but did not verify their email yet
    """

    subject_header_text: str = "Bitte bestätige deine E-Mail-Adresse für Little World"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = "du hast dich kürzlich bei Little World registriert, aber deine E-Mail-Adresse noch nicht bestätigt. Um alle Funktionen unserer Plattform nutzen zu können und mit Menschen aus aller Welt in Kontakt zu treten, bitten wir dich, deine E-Mail-Adresse zu bestätigen."
    content_body_text: str = ""
    link_box_text: str = ""
    button_text: str = "E-Mail-Adresse bestätigen"
    button_link: str = "https://little-world.com/verify-email/"
    below_link_text: str = ""
    footer_text: str = ""
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "finish reminders"


@dataclass
class ConfirmMatchMail1Texts:
    """
    Follow up email about the unfinished userform
    """

    subject_header_text: str = "Match gefunden - jetzt bestätigen"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = "{match_first_name} freut sich schon darauf, dich kennenzulernen! Ihr scheint auch schon eine Menge gemeinsam zu haben. Was das ist, erfährst Du hier:"
    content_body_text: str = ""
    link_box_text: str = ""
    button_text: str = "Jetzt match bestätigen"
    button_link: str = "https://little-world.com/app/"
    below_link_text: str = ""
    footer_text: str = (
        "Dort kannst du auch den Gesprächsvorschlag mit {match_first_name} annehmen. \n"
        + "Du hast Fragen? Wir sind für dich da! Ruf an unter 015234777471 oder schreib uns unter support@little-world.com. Wir helfen dir gerne"
    )
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"
    use_unsubscribe_footer: bool = True


@dataclass
class ConfirmMatchMail2Texts:
    """
    Email to ask user to confirm his match
    """

    subject_header_text: str = "Dein match wartet - höchste Zeit zu bestätigen"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = (
        "du hattest vor Kurzem eine Übereinstimmung auf der Plattform Little World. Gerne würde sich {match_first_name} mit dir unterhalten! Um ihn/sie allerdings nicht zu lange warten zu lassen, werden wir {match_first_name} weitervermitteln, sollten wir nichts von dir hören.\n"
        + "Du möchtest mehr über {match_first_name} erfahren? Dann klicke hier: "
    )
    content_body_text: str = ""
    link_box_text: str = ""
    button_text: str = "Mehr Info"
    button_link: str = "https://little-world.com/app/"
    below_link_text: str = ""
    footer_text: str = (
        "Dort kannst du auch den Gesprächsvorschlag mit {match_first_name} annehmen. \n"
        + "Du hast Fragen? Wir sind für dich da! Ruf an unter {team_phone} oder schreib uns unter {team_email}. Wir helfen dir gerne"
    )
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"
    use_unsubscribe_footer: bool = True


@dataclass
class MatchExpiredMailTexts:
    """
    Email to inform user that their match has expired
    """

    subject_header_text: str = "Dein Match ist abgelaufen - Finde einen neuen Partner"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = (
        "leider ist die Zeit abgelaufen, um {match_first_name} auf der Plattform Little World zu bestätigen. Aber keine Sorge, du kannst dich einloggen und nach einem neuen Match suchen.\n"
        + "Möchtest du jetzt nach einem neuen Match suchen? Dann klicke hier: "
    )
    content_body_text: str = ""
    link_box_text: str = ""
    button_text: str = "Neues Match finden"
    button_link: str = "https://little-world.com/app/"
    below_link_text: str = ""
    footer_text: str = "Du hast Fragen? Wir sind für dich da! Ruf an unter {team_phone} oder schreib uns unter {team_email}. Wir helfen dir gerne"
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"
    use_unsubscribe_footer: bool = True


@dataclass
class InterviewInvitation:
    """
    ---------> Interview invitation email <---------------
    """

    subject_header_text: str = "Einladung zum Online-Interview mit Aniqa"
    greeting: str = "Hallo {first_name}!"
    content_start_text: str = "Mein Name ist Aniqa und ich bin derzeit Studentin an der Universität Siegen im Bereich Human Computer Interaction. Im Rahmen meiner Projektarbeit mit Little World führe ich Online-Interviews mit (englischsprachigen) Ehrenamtlichen durch, um die Nutzererfahrungen mit Little World besser zu verstehen."
    content_body_text: str = mark_safe(
        "Wenn du helfen möchtest die Plattform für andere Benutzer*innen zu verbessern oder einfach eine nette Studentin in ihrer Projektarbeit unterstützen möchtest, dann melde dich bitte bei mir. Nimm gerne einen Kaffee oder Tee zum Online-Interview mit, es wird alles ganz entspannt und dauert nicht mehr als eine Stunde. Ich freue mich auf einen lebhaften Ideenaustausch mit dir!<br></br>Hier ist meine E-Mail-Adresse: "
    )
    link_box_text: str = mark_safe(
        '<a href="mailto:aniqa.rahman@student.uni-siegen.de?subject=Interview" style="color: blue;">aniqa.rahman@student.uni-siegen.de</a>'
    )
    button_text: str = "Interview-Termin buchen"
    button_link: str = "{link_url}"
    below_link_text: str = "Thank you so much for your time,"
    footer_text: str = "PS: das Team von Little World hat diese E-Mail im Namen von Aniqa an dich weitergeleitet. Solltest du in Zukunft keine Interview-Bitten mehr erhalten wollen, so klicke bitte auf E-Mail Abmelden."
    goodbye: str = "Aniqa Rahman"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "special interview request"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class SurveyInvitationAniq2:
    """
    ---------> Survey invitation email <---------------
    """

    subject_header_text: str = "Studentin bittet um Unterstützung – Umfrage bei Little World"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = (
        "Möchtest du uns helfen unsere Little World Plattform zu verbessern oder Aniqa bei ihrer Projektarbeit?"
    )
    link_box_text: str = mark_safe(
        '<a href="https://s.surveyplanet.com/iuhajmj7" style="color: blue;">https://s.surveyplanet.com/iuhajmj7</a>'
    )
    content_body_text: str = (
        " Dann lade ich dich herzlich ein, an der 10-15-minütigen Umfrage von der Studentin Aniqa teilzunehmen unter "
    )
    button_text: str = "Zur Umfrage"
    button_link: str = "{link_url}"
    below_link_text: str = mark_safe(
        "Dein wertvolles Feedback wird uns dabei helfen, die notwendigen Änderungen oder Erweiterungen an unserem Angebot vorzunehmen. Diese Umfrage ist völlig anonym und vertraulich, also teile uns bitte deine ehrlichen Gedanken und Meinungen mit.<br></br>Aniqa ist eine Studentin der Universität Siegen, die derzeit eine Projektarbeit bei uns schreibt. Wenn du Fragen oder Bedenken hast, wende dich gerne jederzeit an uns.<br></br>Vielen Dank im Voraus für deine Unterstützung!"
    )
    footer_text: str = "Herzliche Grüße,"
    goodbye: str = mark_safe("Das Little World Team<br></br>")
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "survey request"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class GeneralSurveyMail:
    """
    ---------> Survey email <---------------
    """

    subject_header_text: str = "Umfrage zur Verbesserung von Little World"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = mark_safe(
        "wir möchten Little World für dich und andere Mitglieder weiter verbessern. Du kannst uns dabei helfen, indem du unsere kurze 3-minütige Umfrage ausfüllst und uns mitteilst, welche Gruppenangebote du dir noch wünschst. Auf die Ergebnisse musst du aber nicht warten. Schon jetzt kannst du dich jeden Dienstag ab 18 Uhr austauschen oder einfach nur zuhören – unverbindlich und in einer kleinen Gruppe. Die beliebtesten Angebote aus unserer Umfrage kommen dann Schritt für Schritt hinzu."
    )
    button_text: str = "ZUR UMFRAGE (google form)"
    button_link: str = "{link_url}"
    content_body_text: str = mark_safe(
        '<br></br>Den Austausch am Dienstag findest du nach dem Einloggen unter "Start" und dann unter "Kaffeeklatsch" oder einfach über folgenden Link:'
    )
    link_box_text: str = mark_safe(
        '<a href="https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09" style="color: blue;">https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09</a>'
    )
    below_link_text: str = ""
    footer_text: str = "Du hast noch Fragen? Melde dich gerne jederzeit - unsere Kontaktdaten findest du in der Signatur. Wir helfen dir gerne weiter."
    goodbye: str = "Dein Team von Little World"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "Von Umfrage E-Mails abmelden"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class ImpulsBeitraegeMail:
    subject_header_text: str = "Impulsbeiträge zum Feierabend"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = mark_safe(
        "Dienstag um 17 Uhr ist es wieder soweit: 5 Minuten Input und eine 10-minütige offene Diskussion. Sei dabei, bei den Impulsvorträgen unserer herzlichen Expertin Raquel Barros und diskutiere mit uns spannende Themen. Wir freuen uns auf einen inspirierenden Austausch mit dir!"
    )
    button_text: str = "ZUM ZOOM CALL (zoom)"
    button_link: str = "{link_url}"
    content_body_text: str = mark_safe(
        'Den Zoom Link für morgen findest du nach dem Einloggen unter "Start" und dann unter "Kaffeeklatsch" oder einfach über den folgenden Link:'
    )
    link_box_text: str = mark_safe(
        '<a href="https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09" style="color: blue;">https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09</a>'
    )
    below_link_text: str = mark_safe("")
    footer_text: str = "Du hast noch Fragen? Melde dich gerne jederzeit - unsere Kontaktdaten findest du in der Signatur. Wir helfen dir gerne weiter."
    goodbye: str = "Dein Team von Little World"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "Von wöchentlichen Impulsbeiträgen E-Mails abmelden"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class ImpulsBeitraegeMail2:
    subject_header_text: str = "Kommende Impulsbeiträge und unser monatliches Come-Together"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = mark_safe(
        "Wir möchten dich herzlich zu unseren nächsten Impulsbeiträgen einladen:"
        '<br/><b>Dienstag, 28.11., 17:00 Uhr:</b> "Fremdreflexion - Achtsamer Umgang #2"'
        '<br/><b>Dienstag, 05.12., 17:00 Uhr:</b> "Out of the Bubble - Achtsamer Umgang #3"'
        "<br></br>Die Teilnahme an den unseren Community Veranstaltungen stehet steht allen offen.<br></br>"
        "<b>Wir möchten dich ermuntern, teilzunehmen und die Gelegenheit zu nutzen, um dich mit anderen auszutauschen und Neues zu entdecken.</b>"
        "<br/><br/>Jeweils 5 Minuten Input und eine 10-minütige offene Diskussion mit unserer erfahrenen Expertin Raquel Barros - "
        "ein Raum für Austausch und Reflexion im interkulturellen Dialog. "
        "<br></br>Außerdem laden wir dich zum <b>monatlichen Come-Together am Donnerstag, 07.12. um 18:00 Uhr</b> ein. "
        "Am ersten Donnerstag jeden Monats vereinen wir unsere Community, um gemeinsam Erfahrungen auszutauschen, "
        "Ideen zur Verbesserung zu besprechen und all deine Fragen zu beantworten."
    )
    button_text: str = "ZUM ZOOM CALL (zoom)"
    button_link: str = "{link_url}"
    content_body_text: str = mark_safe(
        'Den Zoom Link für die kommenden Veranstaltungen findest du nach dem Einloggen unter "Start" > "Kaffeeklatsch" oder direkt über die folgenden Links:'
    )
    link_box_text: str = mark_safe(
        '<a href="https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09" style="color: blue;">https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09</a>'
    )
    footer_text: str = "Solltest du keine weiteren Informationen zu den Impulsbeiträgen wünschen, kannst du dich unten aus dem Verteiler abmelden. Bei Fragen stehen wir dir gerne zur Verfügung - du findest unsere Kontaktdaten in der Signatur. Oder schreib einfach deinem support nutzer."
    goodbye: str = "Wir freuen uns darauf, dich bei den Veranstaltungen zu sehen, und bis dahin – alles Gute!"
    goodbye_name: str = "Dein Team von Little World"
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "event_announcement"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class GeneralSurveyMail_0311:
    """
    ---------> Survey email New 03.11 <---------------
    """

    subject_header_text: str = "Umfrage zur Verbesserung von Little World"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = "Möchtest du uns helfen unsere Little World Plattform zu verbessern?"
    link_box_text: str = mark_safe(
        '<a href="https://tally.so/r/w47d7A" style="color: blue;">https://tally.so/r/w47d7A</a>'
    )
    content_body_text: str = mark_safe(
        "Dann laden wir dich herzlich ein, an der 10-15-minütigen Umfrage teilzunehmen unter "
    )
    button_text: str = "Zur Umfrage"
    button_link: str = "{link_url}"
    below_link_text: str = mark_safe(
        "Dein wertvolles Feedback wird uns dabei helfen, die notwendigen Änderungen oder Erweiterungen an"
        " unserem Angebot vorzunehmen. Diese Umfrage ist völlig anonym und vertraulich, also teile uns bitte"
        " deine ehrlichen Gedanken und Meinungen mit. Wenn du Fragen oder Bedenken hast, wende dich gerne"
        " jederzeit an uns.<br></br>Vielen Dank im Voraus für deine Unterstützung!"
    )
    footer_text: str = "Herzliche Grüße,"
    goodbye: str = mark_safe("Das Little World Team<br></br>")
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = True
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "survey request"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class NewUnreadMessages:
    """
    ---------------> Unread messages mail <--------------------
    """

    subject_header_text: str = "Neue Nachrichten"
    greeting: str = "Hallo {first_name}"
    content_start_text: str = "Du hast neue Nachricht(en) auf Little World erhalten. Du kannst deine Nachrichten in dem Chat von Little World ansehen, indem du auf folgenden Knopf drückst:"
    content_body_text: str = ""
    link_box_text: str = ""  # Empty -> means section auto removed in template rendering
    button_text: str = "Neue Nachrichten anzeigen"
    button_link: str = "https://little-world.com/app/chat"
    below_link_text: str = ""
    footer_text: str = ""
    goodbye: str = "Beste Grüße,"
    goodbye_name: str = "Dein Little World Team"


@dataclass
class PasswordResetEmailTexts:
    reset_subject: str = "Macht doch nichts!"
    reset_body_start: str = "Hier kannst du dein Passwort zurück setzen"
    reset_button_text: str = "Passwort zurücksetzen"
    reset_button_url: str = "{password_reset_url}"


@dataclass
class PasswordResetEmailDefaults:
    reset_subject: str = "reset_subject"
    reset_body_start: str = "reset_body_start"
    reset_button_text: str = "reset_button_text"
    reset_button_url: str = "reset_button_url"


@dataclass
class SorryWeStillNeedALittleMail:
    subject_header_text: str = "Suche & Gruppengespräche"
    greeting: str = "Hi {first_name}"
    content_start_text: str = mark_safe(
        "wow, hunderte von Menschen haben sich in den letzten Wochen für die "
        "<i>Beta-Version</i> von <b>Little World</b> registriert. Vielen Dank euch!"
    )
    content_body_text: str = mark_safe(
        "Unser kleines Team arbeitet auf Hochtouren daran, "
        "für alle die passenden Gesprächspartner:innen zu finden –"
        " das schaffen wir noch nicht überall auf Anhieb. "
        "Dafür möchten wir uns entschuldigen, dafür bieten wir aber auch eine Lösung an." + "<br><br>"
        "Unser Vorschlag: Um schneller zu matchen, erhöhen wir ab <b>Sonntag, 27. November 2022</b>, "
        "den Suchradius auf 100 km. Alle deine anderen Einstellungen bleiben genauso, wie sie waren. "
        "Solltest du aber weiterhin bei „möglichst in der Nähe“ bleiben wollen, ist das auch kein Problem. "
        "Dann antworte ganz einfach auf diese Mail, am besten mit einer maximalen Entfernung." + "<br><br>"
        "Hast du noch Fragen? Dann melde dich jederzeit unter <i>0152 34 777 471</i> oder <i>oliver.berlin@little-world.com</i> oder über den Chat auf unserer Webseite. <br>"
        "Oder besuche unsere <b>Gruppengespräche</b> für Fragen & Anregungen. "
        'Diese findest ab jetzt immer angemeldet auf <a href="www.little-world.com">www.little-world.com</a> unter dem Bereich „Start“ und dann „Kaffeeklatsch“ zu wechselnden Zeiten. '
        " Als nächstes treffen wir uns <b>dienstags 18 - 19 Uhr</b> und <b>donnerstags 13 - 14 Uhr</b>."
    )
    link_box_text: str = ""
    button_text: str = ""
    button_link: str = ""
    below_link_text: str = ""
    footer_text: str = ""
    goodbye: str = "Wir freuen uns über jeden Austausch,"
    goodbye_name: str = "dein Team von Little World"


@dataclass
class NewServerMail:
    subject_header_text: str = "Serverumzug & Neuigkeiten"
    greeting: str = "Liebe Community,"
    content_start_text: str = mark_safe(
        "wir sind umgezogen – es ging auf einen neuen Server. Sorry, sollte es weiterhin zu technischen Problemen kommen. Meldet euch bitte bei unserem Support und wir kümmern uns umgehend darum!"
        " Dieser Schritt war wichtig: für mehr Nutzer:innen, einen schnelleren Matching-Prozess und weitere Features und Verbesserungen, auf die ihr euch bald freuen könnt!"
    )
    content_body_text: str = mark_safe(
        "Wir freuen uns über <b>750 Anmeldungen</b>! Vielen Dank für eure Hilfe, euer Engagement, euer Vertrauen und all die Verbesserungsvorschläge! Unser kleines Team arbeitet auf Hochtouren daran, alles umzusetzen und für alle ein Match zu finden – das schaffen wir noch nicht überall auf Anhieb. Dafür möchten wir uns entschuldigen, dafür bieten wir aber auch eine Lösung an:"
        + "<br><br>"
        "Erzählt anderen Leuten von Little World; folgt uns auf <b>Social Media</b>, teilt unsere Beiträge und helft uns dabei, dass Little World weiter wächst! Denn auch jetzt warten noch mehr als 120 Deutschlernende auf ein Match. Je mehr Leute von uns wissen, desto schneller finden wir für alle Gesprächspartner:innen."
    )
    social_banner_header_text: str = "Ihr findet uns auf folgenden Plattformen:"
    link_box_text: str = ""
    button_text: str = ""
    button_link: str = ""
    below_link_text: str = ""
    footer_text: str = ""
    goodbye: str = "Vielen Dank für eure Unterstützung!"
    goodbye_name: str = (
        "Das gesamte Team von Little World wünscht euch frohe Feiertage und einen guten Rutsch ins neue Jahr!"
    )


@dataclass
class BabbelSubscriptionMail_Winner:
    """
    ---------> Babbel Subscription Winning Email <---------------
    """

    subject_header_text: str = "Herzlichen Glückwunsch! Du hast ein 6-monatiges Babbel-Abonnement gewonnen"
    greeting: str = "Du hast einen Babbel-Gutschein gewonnen!"
    content_start_text: str = (
        "Alle tollen Funktionen und Inhalte von Babbel kannst du jetzt 6 Monate lang kostenlos nutzen."
    )
    content_body_text: str = mark_safe(
        "Nochmals vielen Dank, dass du an unserer Umfrage teilgenommen hast. Um einen kleinen Gefallen möchten wir dich noch bitten: bei Aktivierung des Codes, müsstest du die gleiche Umfrage in 3 Monaten nochmal ausfüllen. Nur so können wir die Auswirkungen der Nutzung von Babbel und Little World messen.<br><br>Du erhältst eine weitere E-Mail von Babbel mit deinem Code und Anweisungen, wie du ihn aktivieren kannst.<br></br>Wenn du Schwierigkeiten mit der Validierung deines Codes hast, melde dich bei uns und wir helfen dir weiter."
    )
    footer_text: str = "Herzliche Grüße,"
    goodbye: str = "Dein Little World Team"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "subscription award"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class GermanImprovementBabbelInvitation:
    """
    ---------> German Improvement with Babbel Code Email <---------------
    """

    subject_header_text: str = "Verbessere dein Deutsch mit einem kostenloser 6-monatiger Babbel Code"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = "Ein Schwerpunkt bei Little World ist es, dir zu helfen, selbstbewusster Deutsch zu sprechen, und wir sind immer auf der Suche nach Möglichkeiten, das zu erreichen... Nun, wir haben uns mit Babbel, einer der führenden Sprach-Apps, zusammengetan und können unseren Nutzern eine Reihe von Gutscheinen kostenlos zur Verfügung stellen."
    content_body_text: str = "Mit diesem Gutschein erhältst du 6 Monate lang Zugang zum Deutschkurs von Babbel. Um einen dieser Gutscheine zu gewinnen, musst du nur diese kurze 3-Minuten-Umfrage ausfüllen."
    button_text: str = "Zur Umfrage"
    button_link: str = "{link_url}"
    below_link_text: str = "Was wollen wir wissen? Wir stellen Fragen, um einen Einblick von deinen derzeitigen Erfahrungen beim Deutschlernen und deinem Leben in Deutschland zu erhalten.Warum wollen wir das wissen? Wir wollen eine Plattform aufbauen, die sich an deinen Bedürfnissen und Erfahrungen orientiert, und dazu möchten wir dir zuhören, um das umzusetzen, was benötigt wird."
    footer_text: str = "Herzliche Grüße,"
    goodbye: str = "Dein Little World Team"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "{unsubscribe_url1}"
    unsubscribe_link1_category: str = "german improvement"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class CommunityGetTogetherInvitation:
    """
    ---------> Community Get-Together Invitation Template <---------------
    """

    subject_header_text: str = "Wir laden dich zu unserem Community Get-Together ein!"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = "möchtest du dich am Donnerstag, den 9. Mai, um 18 Uhr unserem Get-Together anschließen? Als wertvolles Mitglied unserer Little World Community möchten wir mit dir einige Updates teilen und gemeinsam feiern, wie unsere Community wächst."
    content_body_text: str = "Mit mittlerweile über 3.000 Mitgliedern bei Little World trägst du maßgeblich dazu bei, eine inklusive Gesellschaft zu gestalten. Deine Investition von Zeit und Engagement, um Gespräche zu führen und andere zu unterstützen, ist von unschätzbarem Wert, damit wir uns alle wohl und geschätzt fühlen. Gemeinsam haben wir bereits über 160 multikulturelle Gespräche in 2024 geführt, mit über 120 wirkungsvollen Stunden! Als Community zeigen wir, wie aus demokratischen Werten konkrete Taten werden. Im Call möchten wir teilen, wo wir heute als gemeinnütziges Start-up dank deiner Mitwirkung stehen und was wir für 2024 vorhaben, um gemeinsam weiter zu wachsen. Wir sind sehr gespannt darauf, deine Ideen und deine Erfahrungen zu hören. Denn nur durch deine wertvolle Mitwirkung können wir Little World gemeinsam noch besser machen."
    button_text: str = "Zum Call beitreten"
    button_link: str = "https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09"
    link_box_text: str = mark_safe(
        '<a href="https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09" style="color: blue;">https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09</a>'
    )
    below_link_text: str = "Wir freuen uns schon riesig auf dich und deinen Beitrag!"
    footer_text: str = "Liebe Grüße,"
    goodbye: str = "Oliver, Tim, Sean und Melina"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "none"
    unsubscribe_link1_category: str = "none"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


class TrainingSeriesInvitation:
    """
    ---------> Community Training Series Invitation Template <---------------
    """

    subject_header_text: str = (
        "Dankeschön für deine Teilnahme am Get-together & Ankündigung der interkulturellen Trainingsserie!"
    )
    greeting: str = "Liebe {first_name},"
    content_start_text: str = (
        "wir hoffen, dass diese Woche für dich gut begonnen hat! Letzten Donnerstag hatten wir unser Get-Together. "
        "Es war großartig, gemeinsam mit vielen Mitgliedern unserer Little World Community unsere Erfolge zu feiern. "
        "In unserer Community trägt jedes Gespräch dazu bei, eine Gesellschaft zu gestalten, die von Verständnis und Empathie geprägt ist, "
        "in der sich jeder willkommen und geschätzt fühlt."
    )
    content_body_text: str = mark_safe(
        "Nun freuen wir uns, dir eine aufregende neue Initiative anzukündigen: Ab nächster Woche starten wir eine interkulturelle Trainingsserie für unsere Community! "
        "Wir haben Raquel Barros, die Leiterin der Werkstatt der Kulturen beim Diakonischen Werk im Kirchenkreis Aachen e.V., eingeladen, und sie wird uns durch 6 Trainings führen. "
        "Diese Serie zielt darauf ab, unsere Fähigkeit zu entwickeln, kulturelle Unterschiede und Vielfalt in einem globalen Kontext zu verstehen, anzuerkennen und damit umzugehen. "
        "Auch wenn du nicht an allen 6 Terminen teilnehmen kannst, ist das kein Problem, denn jede Session bietet ein vollständiges Training für sich allein.<br><br>"
        "Hier sind die Termine für die interkulturelle Trainingsserie:<br><br>"
        "<ul>"
        "<li>Montag, 20. Mai, 18 Uhr - 1: Interkulturelle Begegnung - Achtsamer Umgang</li>"
        "<li>Montag, 27. Mai, 18 Uhr - 2: Selbstreflexion - Achtsamer Umgang</li>"
        "<li>Montag, 3. Juni, 18 Uhr - 3: Fremdreflexion - Achtsamer Umgang</li>"
        "<li>Montag, 10. Juni, 18 Uhr - 4: Achtsamer Umgang miteinander – Out of the Bubble</li>"
        "<li>Montag, 17. Juni, 18 Uhr - 5: Theorie muss sein: Kulturdimensionen</li>"
        "<li>Montag, 24. Juni, 18 Uhr - 6: Interkulturelles Training – Sensibilisierung</li>"
        "</ul>"
        'Alle Termine sind auf unserer Plattform verfügbar und können im Bereich "Gruppengespräche" unter "Start" gefunden werden. '
        "Wir hoffen, dass du dabei sein kannst, denn man lernt nie aus! Diese Impulse werden uns allen helfen, uns weiterzuentwickeln.<br><br>"
        "Wir möchten uns noch einmal herzlich bei dir für deine Unterstützung und deine wertvollen Beiträge zur Little World Community bedanken. "
        "Gemeinsam machen wir Little World zu einem besseren Ort für alle."
    )
    button_text: str = ""
    button_link: str = ""
    link_box_text: str = ""
    below_link_text: str = ""
    footer_text: str = "Mit herzlichen Grüßen,"
    goodbye: str = "Oliver, Tim, Sean und Melina"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "none"
    unsubscribe_link1_category: str = "none"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class CulturalAwarenessInvitation:
    """
    ---------> Community Cultural Awareness Invitation Template <---------------
    """

    subject_header_text: str = "Einladung zu unseren interkulturellen Treffen!"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = (
        "wir bei Little World wollen, dass alle Menschen sich gut verstehen, auch wenn sie aus verschiedenen Ländern kommen. "
        "Deshalb haben wir mehrere Treffen organisiert, bei denen wir lernen, wie wir die Unterschiede zwischen den Kulturen verstehen und schätzen können."
    )
    content_body_text: str = mark_safe(
        "Jeden Montag wird uns Raquel Barros von der Werkstatt der Kulturen besuchen. Sie wird uns in ganz einfacher Sprache erklären, worum es geht. "
        "Wenn du B1 Deutsch verstehen kannst, wirst du sicher alles verstehen! Es ist auch eine gute Möglichkeit, dein Deutsch zu üben. "
        "Und wenn du Fragen hast, kannst du uns alles fragen. Wir sind hier, um alle gemeinsam zu lernen.<br><br>"
        "Nach dem kurzen Vortrag gibt es Zeit für Fragen und zum Reden. Du kannst dich gerne beteiligen! "
        "Bei Little World sind wir wie eine große Community und wir machen alle mal Fehler. Also keine Angst, nutze die Chance, um etwas zu lernen und dein Deutsch zu verbessern.<br><br>"
        "Hier sind die Termine für die interkulturellen Treffen:<br><br>"
        "<ul>"
        "<li>Montag, 20. Mai, 18 Uhr - 1: Interkulturelle Begegnung - Achtsamer Umgang</li>"
        "<li>Montag, 27. Mai, 18 Uhr - 2: Selbstreflexion - Achtsamer Umgang</li>"
        "<li>Montag, 3. Juni, 18 Uhr - 3: Fremdreflexion - Achtsamer Umgang</li>"
        "<li>Montag, 10. Juni, 18 Uhr - 4: Achtsamer Umgang miteinander – Out of the Bubble</li>"
        "<li>Montag, 17. Juni, 18 Uhr - 5: Theorie muss sein: Kulturdimensionen</li>"
        "<li>Montag, 24. Juni, 18 Uhr - 6: Interkulturelles Training – Sensibilisierung</li>"
        "</ul>"
        "Merke sie dir in deinem Kalender und du kannst einfach über den Link auf unserer Website an den Treffen teilnehmen. Da stehen alle Termine.<br><br>"
        "PS: Möchtest du dich auf das Gespräch vorbereiten? Wir haben ein kleines Glossar mit typischen Worten in diesem Thema, die vielleicht schwierig sein können. "
        'So kennst du sie alle, bevor es startet. <a href="https://home.little-world.com/wp-content/uploads/2024/05/Glossar-Trainings.pdf" style="color: blue;">(Link)</a>.'
    )
    button_text: str = ""
    button_link: str = ""
    link_box_text: str = ""
    below_link_text: str = ""
    footer_text: str = "Liebe Grüße,"
    goodbye: str = "Oliver, Tim, Sean und Melina"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "none"
    unsubscribe_link1_category: str = "none"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class CommunityGetTogetherInvitation120624:
    """
    ---------> Community Get-Together Invitation Template <---------------
    """

    subject_header_text: str = "Wir laden dich zu unserem Community Get-Together ein!"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = "diesen Donnerstag, den 13. Juni, um 18 Uhr ist unser monatliches Community Get Together. Bist du auch dabei? 😊"
    content_body_text: str = "Wir freuen uns auf viele Teilnehmer. Dies ist unsere Chance, zusammenzukommen und uns auszutauschen. Alle sind willkommen – Menschen, die Deutsch als Muttersprache sprechen, und auch diejenigen, die gerade Deutsch lernen. Es wird eine tolle Gelegenheit sein, unsere Erfolge zu feiern, Feedback und Ideen auszutauschen und uns besser kennenzulernen. 🥳"
    button_text: str = "Zum Call beitreten"
    button_link: str = "https://rwth.zoom.us/j/61394184102"
    link_box_text: str = mark_safe(
        '<a href="https://rwth.zoom.us/j/61394184102" style="color: blue;">https://rwth.zoom.us/j/61394184102</a>'
    )
    below_link_text: str = "Sei dabei! Unter diesem Link kannst du direkt am Donnerstag um 18 Uhr teilnehmen:"
    footer_text: str = "Liebe Grüße,"
    goodbye: str = "Oliver, Tim, Sean und Melina"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "none"
    unsubscribe_link1_category: str = "none"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class CommunityGetTogetherInvitationToday:
    """
    ---------> Community Get-Together Invitation Template <---------------
    """

    subject_header_text: str = "Wir laden dich zu unserem heutigen Community Get-Together ein!"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = "heute, Donnerstag, den 13. Juni, um 18 Uhr ist unser monatliches Community Get Together. Bist du auch dabei? 😊"
    content_body_text: str = "Wir freuen uns auf viele Teilnehmer. Dies ist unsere Chance, zusammenzukommen und uns auszutauschen. Alle sind willkommen – Menschen, die Deutsch als Muttersprache sprechen, und auch diejenigen, die gerade Deutsch lernen. Es wird eine tolle Gelegenheit sein, unsere Erfolge zu feiern, Feedback und Ideen auszutauschen und uns besser kennenzulernen. 🥳"
    button_text: str = "Zum Call beitreten"
    button_link: str = "https://rwth.zoom.us/j/61394184102"
    link_box_text: str = mark_safe(
        '<a href="https://rwth.zoom.us/j/61394184102" style="color: blue;">https://rwth.zoom.us/j/61394184102</a>'
    )
    below_link_text: str = "Sei dabei! Unter diesem Link kannst du direkt heute um 18 Uhr teilnehmen:"
    footer_text: str = "Liebe Grüße,"
    goodbye: str = "Oliver, Tim, Sean und Melina"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "none"
    unsubscribe_link1_category: str = "none"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class CultureDimensionsLectureInvitationToday:
    """
    ---------> Culture Dimensions Lecture Invitation Template <---------------
    """

    subject_header_text: str = "Einladung zum heutigen Vortrag über Kulturdimensionen 🌍"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = "heute, Montag, den 24. Juni, um 18 Uhr spricht Raquel Barros über Kulturdimensionen. In ihrem 10-minütigen Vortrag erklärt sie die Theorie der Kulturdimensionen. Du musst nicht an den vorherigen Vorträgen teilgenommen haben, um dabei zu sein. Dieser Vortrag ist ein komplettes Thema für sich."
    content_body_text: str = "Das ist eine tolle Chance, mehr über dieses Thema zu lernen und dein Wissen zu erweitern. Raquel Barros ist die Leiterin der Werkstatt der Kulturen beim Diakonischen Werk im Aachen e.V. und hat viel Erfahrung. Nach dem Vortrag haben wir Zeit für Fragen und eine Diskussion. So können wir das Gelernte zusammen besprechen. Wir freuen uns sehr, wenn du dabei bist!"
    button_text: str = "Zum Vortrag beitreten"
    button_link: str = "https://rwth.zoom.us/j/67464220489"
    link_box_text: str = mark_safe(
        '<a href="https://rwth.zoom.us/j/67464220489" style="color: blue;">https://rwth.zoom.us/j/67464220489</a>'
    )
    below_link_text: str = "Klicke einfach auf diesen Link, um heute um 18 Uhr teilzunehmen. Oder logge dich bei Little World ein und du findest den Link unter “Gruppengespräche”."
    footer_text: str = "Falls dir einige Begriffe nicht bekannt sind, kannst du dich mit diesem Glossar vorbereiten: "
    glossary_link: str = mark_safe(
        '<a href="https://home.little-world.com/wp-content/uploads/2024/05/Glossar-Trainings.pdf" style="color: blue;">Glossar (link zum Glossar)</a>'
    )
    goodbye: str = "Liebe Grüße,"
    goodbye_name: str = "Oliver, Tim, Sean und Melina 😊"
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "none"
    unsubscribe_link1_category: str = "none"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class CommunityGetTogetherInvitation130624:
    """
    ---------> Community Get Together Invitation Template <---------------
    """

    subject_header_text: str = "Einladung zum Community Get Together am Donnerstag 🎉"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = "diesen Donnerstag, den 4. Juli, um 18 Uhr treffen wir uns zu unserem Community Get-together! Hier kommen das gesamte Team, Deutschlernende und Ehrenamtliche zusammen. Gemeinsam feiern wir die Erfolge und die Wirkung, die wir in der ersten Hälfte dieses Jahres erzielt haben. Komm einfach vorbei und nutze die Chance, andere Menschen kennenzulernen, die sich wie du für unsere vielfältige Gesellschaft engagieren."
    content_body_text: str = "Wir freuen uns auf dich! Mit diesem Link kommst du direkt in den Call:"
    button_text: str = "Zum Event beitreten"
    button_link: str = "https://rwth.zoom.us/j/61394184102"
    link_box_text: str = mark_safe(
        '<a href="https://rwth.zoom.us/j/61394184102" style="color: blue;">https://rwth.zoom.us/j/61394184102</a>'
    )
    below_link_text: str = mark_safe("<br></br>")
    footer_text: str = ""
    glossary_link: str = ""
    goodbye: str = "Liebe Grüße,"
    goodbye_name: str = "Oliver, Tim, Sean und Melina 😊"
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "none"
    unsubscribe_link1_category: str = "none"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class ReActivateVolunteers:
    """
    ---------> Community Cultural Awareness Invitation Template <---------------
    """

    subject_header_text: str = "Wir vermissen Dich – Deine Unterstützung zählt!"
    greeting: str = "Liebe/r {first_name},"
    content_start_text: str = "wir hoffen, es geht Dir gut und Du genießt den Sommer! 😊"
    content_body_text: str = mark_safe(
        "Wir haben Dich bei unserem Onboarding-Termin vermisst und wollten Dich daran erinnern, wie wichtig Deine Unterstützung für uns und die Deutschlernenden ist. "
        "Dein Engagement hilft uns dabei, eine inklusive Gesellschaft zu fördern, in der alle die Vielfalt genießen können.<br><br>"
        "Vielleicht hast Du im Sommer etwas mehr Freizeit... Aber auch wenn Du diesen Sommer im Urlaub bist, ist das kein Problem! Du kannst ganz einfach mit Deinem Gesprächspartner vereinbaren, ein paar Wochen zu pausieren, bis Du zurück bist.<br><br>"
        "Deswegen möchten wir Dich herzlich einladen, einen der nächsten Onboarding-Termine wahrzunehmen:<br><br>"
        "<ul>"
        "<li>Freitag, 19. Juli 15:30 Uhr</li>"
        "<li>Mittwoch, 24. Juli 18:30 Uhr</li>"
        "<li>Freitag, 26. Juli 10:30 Uhr</li>"
        "<li>Dienstag, 30. Juli 17:00 Uhr</li>"
        "</ul>"
        "<br>"
        "Logge Dich einfach in Deinen Account ein und wähle einen Termin aus."
        "Deine Teilnahme macht einen großen Unterschied und wir freuen uns sehr auf Deine Unterstützung. Falls Du Fragen hast oder Hilfe benötigst, zögere nicht, uns zu kontaktieren."
    )
    button_text: str = "Onboarding-Termin buchen"
    button_link: str = "https://little-world.com/login"
    link_box_text: str = ""
    below_link_text: str = ""
    footer_text: str = "Herzliche Grüße,"
    goodbye: str = "Das gesamte Little World Team"
    goodbye_name: str = ""
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "none"
    unsubscribe_link1_category: str = "none"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"


@dataclass
class CommunityGetTogetherInvitation010824:
    """
    ---------> Community Get Together Invitation Template <---------------
    """

    subject_header_text: str = "Einladung zum Community Get Together am Donnerstag 🎉"
    greeting: str = "Hallo {first_name},"
    content_start_text: str = "diesen Donnerstag, den 1. August, um 18 Uhr treffen wir uns zu unserem Community Get-together! Hier kommen das gesamte Team, Deutschlernende und Ehrenamtliche zusammen. Gemeinsam feiern wir die Erfolge und die Wirkung, die wir in der ersten Hälfte dieses Jahres erzielt haben. Komm einfach vorbei und nutze die Chance, andere Menschen kennenzulernen, die sich wie du für unsere vielfältige Gesellschaft engagieren."
    content_body_text: str = "Wir freuen uns auf dich! Mit diesem Link kommst du direkt in den Call:"
    button_text: str = "Zum Event beitreten"
    button_link: str = "https://rwth.zoom.us/j/61394184102"
    link_box_text: str = mark_safe(
        '<a href="https://rwth.zoom.us/j/61394184102" style="color: blue;">https://rwth.zoom.us/j/61394184102</a>'
    )
    below_link_text: str = mark_safe("<br></br>")
    footer_text: str = ""
    glossary_link: str = ""
    goodbye: str = "Liebe Grüße,"
    goodbye_name: str = "Oliver, Tim, Sean und Melina 😊"
    use_unsubscribe_footer: bool = False
    unsubscribe_two_link: bool = False
    unsubscribe_link1: str = "none"
    unsubscribe_link1_category: str = "none"
    unsubscribe_link2: str = "none"
    unsubscribe_link2_category: str = "none"
