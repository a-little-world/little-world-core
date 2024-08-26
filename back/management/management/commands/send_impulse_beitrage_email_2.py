from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, **options):
        from management.models.matches import Match
        from management.models.state import State
        from management.models.user import User
        from django.db.models import Q
        from django.utils import timezone
        import datetime

        from emails import mails

        consider_only_registered_within_last_x_days = 120

        today = timezone.now()
        all_users_to_consider = User.objects.filter(~(Q(state__user_category=State.UserCategoryChoices.SPAM) | Q(state__user_category=State.UserCategoryChoices.TEST)), state__user_form_state=State.UserFormStateChoices.FILLED, state__email_authenticated=True, is_staff=False)

        x_days_ago = today - datetime.timedelta(days=consider_only_registered_within_last_x_days)
        all_users_to_consider = all_users_to_consider.filter(date_joined__gte=x_days_ago)

        def get_params(user):
            return mails.ImpulseBeitraegeParams2(
                first_name=user.profile.first_name,
                link_url="https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09",
                unsubscribe_url1="",  # filled automatically
            )

        from management import controller

        print("check which users to send to or just send a test email? (Y/N)")
        user_input = input()

        if user_input == "Y":
            print("Sending emails...")
            users = list(all_users_to_consider)
            users = filter(lambda user: not (("oliver" in user.email) or ("rwth" in user.email) or ("berlin" in user.email) or ("hauptstadt" in user.email)), users)
            users = list(users)

            print("Collected", len(users), "users to send to")
            print("\n".join(map(lambda user: user.email, users)))
            print("send it ?( Y/N)")

            user_input = input()
            if user_input == "Y":
                controller.send_group_mail(users=users, subject="Kommende Impulsbeiträge und unser monatliches Come-Together", mail_name="impuls_beitraege2", mail_params_func=get_params, unsubscribe_group="event_announcement")
            else:
                print("Not send")
        else:
            print("Do nothing...")
            print("Send Test Email to tim.timschupp+420@gmail.com (Y/N) ?")

            users = [controller.get_user_by_email("tim.timschupp+420@gmail.com")]
            controller.send_group_mail(users=users, subject="Kommende Impulsbeiträge und unser monatliches Come-Together", mail_name="impuls_beitraege2", mail_params_func=get_params, unsubscribe_group="event_announcement")

        MESSAGE_ANNOUNCEMENT = """
<span class="announcement-badge">Ankündigung</span>
<div class="text-content">
<b>Herzliche Einladung zu unseren Impulsbeiträgen</b>
</div>
<label for="toggle-announcement" class="show-button">Show</label>
<input type="checkbox" id="toggle-announcement" class="toggle-checkbox">
<div class="announcement-message">
<div class="text-content">
Einmal pro Woche finden bei uns Vorträge und Veranstaltungen statt. Im Moment gibt es eine Reihe an Impulsbeiträgen zu verschiedenen Themen. <br>
• <span class="emphasis-text">Fremdreflexion - Achtsamer Umgang #2</span>: <b>Dienstag, 28.11., 17:00 Uhr</b><br>
• <span class="emphasis-text">Out of the Bubble - Achtsamer Umgang #3</span>: <b>Dienstag, 05.12., 17:00 Uhr</b><br>
Jeweils 5 Minuten Input und eine 10-minütige offene Diskussion mit unserer erfahrenen Expertin Raquel Barros - ein Raum für Austausch und Reflexion im interkulturellen Dialog. <br>
<span class="strong-text">Auch ist bald unser Monatliches Come-Together:</span><br>
• <b>Donnerstag, 07.12., 18:00 Uhr</b>: Ein Raum für Austausch in unserer Community.
Bereitschaft zu lernen und zu teilen ist der erste Schritt zur Verbesserung. <br>
<span class="strong-text"><b>Die Veranstaltungen sind offen für alle, Wir freuen uns auf deine Teilnahme!</b></span>
Den Zoom Link für die kommenden Veranstaltungen findest du nach dem Einloggen unter "Start" > "Kaffeeklatsch" oder direkt über folgenden Knopf:
</div>
<div class="zoom-button-container">
<a href="https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09" target="_blank" class="zoom-button">Zum Zoom Meeting</a>
</div>
</div>"""
        print("Also send message announcement? (Y/N)")
        user_input = input()
        if user_input == "Y":
            total = len(users)
            i = 0
            for user in users:
                print("Sending message announcement to", user.email, "(", i, "/", total, ")")
                i += 1
                tim_is_support = str(Match.get_support_matches(user).first().get_partner(user).email).startswith("tim.timschupp+420@gmail.com")
                if tim_is_support:
                    user.message(MESSAGE_ANNOUNCEMENT)
                else:
                    print("Not sending message announcement to", user.email, "since tim is not support")
        else:
            print("sending message announcement ONLY to herrduenschnlate@gmail.com	")
            controller.get_user_by_email("herrduenschnlate@gmail.com").message(MESSAGE_ANNOUNCEMENT)
