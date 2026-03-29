from django.core.management.base import BaseCommand

from management.models.matches import Match


class Command(BaseCommand):
    def handle(self, **options):
        all_matches = Match.objects.all()

        print(f"Total matches: {all_matches.count()}")

        c = 0
        for match in all_matches.iterator():
            c += 1
            if c % 100 == 0:
                print(f"Processing match {c} of {all_matches.count()}")

            match.auto_email_m043_send = False
            match.auto_email_m044_send = False
            match.auto_email_m045_send = False
            match.save(update_fields=["auto_email_m043_send", "auto_email_m044_send", "auto_email_m045_send"])

        print(f"Done! Processed {c} matches.")
