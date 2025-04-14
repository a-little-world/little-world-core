from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, **options):
        from emails import mails

        from management.tasks import send_email_background
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
                for user in users:
                    send_email_background.delay(
                        template_name="reactivate_volunteers"
                    )
            else:
                print("Not send")
        else:
            print("Do nothing...")
            