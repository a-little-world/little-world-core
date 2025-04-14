from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, **options):
        from emails import mails

        from management.tasks import send_email_background
        from management.api.user_journey_filters import all_volunteers_min_one_no_ongoing_match
        from management import controller

        all_users_to_consider = all_volunteers_min_one_no_ongoing_match()
        users = list(all_users_to_consider)

        print("Collected", len(users), "users to send to")
        print("check which users to send to or just send a test email? (Y/N)")
        user_input = input()

        if user_input == "Y":
            print("\n".join(map(lambda user: user.email, users)))
            print(f"Send email to {len(users)} users? (Y/N)")

            user_input = input()
            if user_input == "Y":
                total = len(users)
                for i, user in enumerate(users, 1):
                    print(f"Sending email ({i}/{total}) to {user.email}")
                    send_email_background.delay(
                        template_name="reactivate_volunteers",
                        user_id=user.id
                    )
                print(f"Successfully scheduled {total} emails")
            else:
                print("Emails not sent")
        else:
            print("Do you want to send a test email? (Y/N)")
            user_input = input()
            if user_input == "Y":
                test_email = input("Enter test email address: ")
                try:
                    test_user = controller.get_user_by_email(test_email)
                    print(f"Sending test email to {test_user.email}")
                    send_email_background.delay(
                        template_name="reactivate_volunteers",
                        user_id=test_user.id
                    )
                    print("Test email scheduled")
                except Exception as e:
                    print(f"Error: {e}")
            else:
                print("Do nothing...")
            