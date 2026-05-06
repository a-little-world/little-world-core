from django.core.management.base import BaseCommand

from management.permissions import ManagementPermission


class Command(BaseCommand):
    def handle(self, **options):
        from django.db.models import Q

        from management.models.matches import Match

        # Get all matches where at least one user has matching user permission
        matchesToUpdate = Match.objects.filter(
            Q(
                user1__user_permissions__content_type__app_label="management",
                user1__user_permissions__content_type__model="state",
                user1__user_permissions__codename=ManagementPermission.MATCHING_USER.codename,
            )
            | Q(
                user2__user_permissions__content_type__app_label="management",
                user2__user_permissions__content_type__model="state",
                user2__user_permissions__codename=ManagementPermission.MATCHING_USER.codename,
            )
        )

        # Update all matches to support_matching = True in one go
        matchesToUpdate.update(support_matching=True)

        print(f"Updated {matchesToUpdate.count()} matches.")
