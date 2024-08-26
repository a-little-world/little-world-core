from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, **options):
        from management.models.matches import Match
        from management.models.state import State

        from django.db.models import Q

        # Get all matches where at least one user has matching user permission
        matchesToUpdate = Match.objects.filter(Q(user1__state__extra_user_permissions__contains=State.ExtraUserPermissionChoices.MATCHING_USER) | Q(user2__state__extra_user_permissions__contains=State.ExtraUserPermissionChoices.MATCHING_USER))

        # Update all matches to support_matching = True in one go
        matchesToUpdate.update(support_matching=True)

        print(f"Updated {matchesToUpdate.count()} matches.")
