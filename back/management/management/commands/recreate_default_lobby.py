from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from video.models import RandomCallLobby


class Command(BaseCommand):
    help = "Delete and recreate the default random call lobby with current time"

    def handle(self, *args, **options):
        # Delete existing default lobby
        deleted_count, _ = RandomCallLobby.objects.filter(name="default").delete()
        
        if deleted_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"Deleted {deleted_count} existing 'default' lobby(s)")
            )
        else:
            self.stdout.write(self.style.WARNING("No existing 'default' lobby found"))
        
        # Create new default lobby with current time
        lobby = RandomCallLobby.objects.create(name="default")
        lobby.start_time = timezone.now()
        lobby.end_time = timezone.now() + timedelta(days=1)
        lobby.save()
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Created new 'default' lobby with start_time={lobby.start_time} "
                f"and end_time={lobby.end_time}"
            )
        )

