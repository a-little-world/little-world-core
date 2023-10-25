from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def handle(self, **options):
        from emails.models import EmailLog
        
        print(f"Deleting all still in contact reminders, that are more recent than 120 days.")
        
        all_still_in_contact_reminders = EmailLog.objects.filter(
            template="still_in_contact"
        )
        
        print(f"Found {all_still_in_contact_reminders.count()} still in contact reminders.")
        print(f"Y = Yes, N = No, To delete all still in contact reminders, type 'Y' and press enter.")
        
        user_input = input()

        if user_input == "Y":
            all_still_in_contact_reminders.delete()
            print(f"Deleted all still in contact reminders.")
        else:
            print(f"Did not delete all still in contact reminders.")