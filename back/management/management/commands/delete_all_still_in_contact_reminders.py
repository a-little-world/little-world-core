from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, **options):
        from emails.models import EmailLog

        print("Deleting all still in contact reminders, that are more recent than 120 days.")

        all_still_in_contact_reminders = EmailLog.objects.filter(template="still_in_contact")

        print(f"Found {all_still_in_contact_reminders.count()} still in contact reminders.")
        print("Y = Yes, N = No, To delete all still in contact reminders, type 'Y' and press enter.")

        user_input = input()

        if user_input == "Y":
            all_still_in_contact_reminders.delete()
            print("Deleted all still in contact reminders.")
        else:
            print("Did not delete all still in contact reminders.")
