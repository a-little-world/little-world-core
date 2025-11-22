from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from video.models import RandomCallLobby, RandomCallLobbyUser, RandomCallMatching


class Command(BaseCommand):
    help = "Delete and recreate the default random call lobby with current time"

    def handle(self, *args, **options):
        # Get the existing lobby first
        existing_lobby = RandomCallLobby.objects.filter(name="default").first()
        
        if existing_lobby:
            # Clear all lobby users
            lobby_users_count, _ = RandomCallLobbyUser.objects.filter(lobby=existing_lobby).delete()
            if lobby_users_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f"Deleted {lobby_users_count} lobby user(s)")
                )
            
            # Clear all matchings
            matchings_count, _ = RandomCallMatching.objects.filter(lobby=existing_lobby).delete()
            if matchings_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f"Deleted {matchings_count} matching(s)")
                )
            
            # Delete the lobby itself
            existing_lobby.delete()
            self.stdout.write(
                self.style.SUCCESS("Deleted existing 'default' lobby")
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


