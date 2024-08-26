from video.models import LiveKitRoom
from management.models.matches import Match
from django.core.management.base import BaseCommand
from django.db.models import Q


class Command(BaseCommand):
    def handle(self, *args, **options):
        all_matches = Match.objects.all()
        total = all_matches.count()

        c = 0
        for maching in all_matches:
            room = LiveKitRoom.objects.filter(Q(u1=maching.user1, u2=maching.user2) | Q(u1=maching.user2, u2=maching.user1))
            print(f"( {c}/{total} ) Checking match {maching.uuid}...")
            if not room.exists():
                room = LiveKitRoom.objects.create(
                    u1=maching.user1,
                    u2=maching.user2,
                )
                print(f"Created room for match {maching.uuid}")
            c += 1
