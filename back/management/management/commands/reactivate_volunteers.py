from django.core.management.base import BaseCommand


# e.g.:
# 'python3 manage.py reactivate_volunteers --list herrduenschnlate'
# 'python3 manage.py reactivate_volunteers --list TEST__all_volunteers_min_one_no_ongoing_match'
class Command(BaseCommand):
    help = "Send reactivation emails to users based on a specified filter list"

    def add_arguments(self, parser):
        parser.add_argument(
            "--list",
            type=str,
            default="TEST__all_volunteers_min_one_no_ongoing_match",
            help="Name of the filter list to use (from user_advanced_filter_lists.py)",
        )
        parser.add_argument(
            "--test-only",
            action="store_true",
            help="Only allow sending test emails, not bulk emails",
        )

    def handle(self, *args, **options):
        from emails import mails
        from management.tasks import send_email_background
        from management import controller
        from management.api.user_advanced_filter_lists import get_list_by_name

        list_name = options["list"]
        test_only = options["test_only"]
        
        # Get the base management user
        management_user = controller.get_base_management_user()
        
        # Get the filter list entry by name
        filter_list_entry = get_list_by_name(list_name)
        
        if not filter_list_entry:
            self.stdout.write(self.style.ERROR(f"Filter list '{list_name}' not found"))
            return
        
        # Pre-filter users to only include those managed by the base management user
        pre_filtered_users = management_user.state.managed_users.all()
        
        # Apply the selected filter to the pre-filtered users
        all_users_to_consider = filter_list_entry.queryset(qs=pre_filtered_users)
        users = list(all_users_to_consider)

        self.stdout.write(f"Using filter list: {list_name}")
        self.stdout.write(f"Description: {filter_list_entry.description or 'No description'}")
        self.stdout.write(f"Collected {len(users)} users to send to")
        
        if test_only:
            self.stdout.write("Running in test-only mode. Bulk emails disabled.")
            self.handle_test_email()
        else:
            self.stdout.write("Check which users to send to or just send a test email? (Y/N)")
            user_input = input()

            if user_input == "Y":
                self.handle_bulk_emails(users)
            else:
                self.handle_test_email()

    def handle_bulk_emails(self, users):
        from management.tasks import send_email_background
        
        self.stdout.write("\n".join(map(lambda user: user.email, users)))
        self.stdout.write(f"Send email to {len(users)} users? (Y/N)")

        user_input = input()
        if user_input == "Y":
            total = len(users)
            for i, user in enumerate(users, 1):
                self.stdout.write(f"Sending email ({i}/{total}) to {user.email}")
                send_email_background.delay(
                    template_name="reactivate_volunteers",
                    user_id=user.id
                )
            self.stdout.write(self.style.SUCCESS(f"Successfully scheduled {total} emails"))
        else:
            self.stdout.write("Emails not sent")

    def handle_test_email(self):
        from management import controller
        from management.tasks import send_email_background
        
        self.stdout.write("Do you want to send a test email? (Y/N)")
        user_input = input()
        if user_input == "Y":
            test_email = input("Enter test email address: ")
            try:
                test_user = controller.get_user_by_email(test_email)
                self.stdout.write(f"Sending test email to {test_user.email}")
                send_email_background.delay(
                    template_name="reactivate_volunteers",
                    user_id=test_user.id
                )
                self.stdout.write(self.style.SUCCESS("Test email scheduled"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error: {e}"))
        else:
            self.stdout.write("Do nothing...")
            