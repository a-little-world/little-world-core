from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, **options):
        from emails import mails

        from management.models.matches import Match
        from management.api.user_journey_filters import all_volunteers_min_one_no_ongoing_match

        all_users_to_consider = all_volunteers_min_one_no_ongoing_match()

        def get_params(user):
            return mails.ReActivateVolunteersParams(
                first_name=user.profile.first_name
            )

        from management import controller

        print("check which users to send to or just send a test email? (Y/N)")
        user_input = input()

        if user_input == "Y":
            users = list(all_users_to_consider)
            
            print("Collected", len(users), "users to send to")
            print("\n".join(map(lambda user: user.email, users)))
            print("send it ?( Y/N)")

            user_input = input()
            if user_input == "Y":
                controller.send_group_mail(
                    users=users,
                    subject="Wir vermissen Dich – Deine Unterstützung zählt!",
                    mail_name="reactivate_volunteers",
                    mail_params_func=get_params,
                    unsubscribe_group="none",
                )
            else:
                print("Not send")
        else:
            print("Do nothing...")
            