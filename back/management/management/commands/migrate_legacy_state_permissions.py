from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from management.models.state import State

PERMISSION_DEFINITIONS = [
    ("view_api_schema", "Can view API schema"),
    ("view_database_schema", "Can view database schema"),
    ("matching_user", "Can perform matching operations"),
    ("use_random_calls", "Can use random calls feature"),
]

LEGACY_TO_CODENAME = {
    "view-api-schema": "view_api_schema",
    "view-database-schema": "view_database_schema",
    "matching-user": "matching_user",
    "use-random-calls": "use_random_calls",
}

DEPRECATED_PERMISSION_CODENAMES = [
    "use_autologin_api",
    "view_docs",
    "view_email_templates",
    "view_stats",
    "uncensored_admin_matcher",
]


def _to_permission_list(raw_value):
    if not raw_value:
        return []

    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(",") if item.strip()]

    if isinstance(raw_value, (list, tuple, set)):
        return [str(item).strip() for item in raw_value if str(item).strip()]

    return []


class Command(BaseCommand):
    help = "Backfill Django auth permissions from legacy state.extra_user_permissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be changed without writing database updates.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        state_content_type, _ = ContentType.objects.get_or_create(app_label="management", model="state")
        deprecated_permissions = list(
            Permission.objects.filter(
                content_type=state_content_type,
                codename__in=DEPRECATED_PERMISSION_CODENAMES,
            )
        )

        users_with_deprecated_permissions = 0
        groups_with_deprecated_permissions = 0
        deprecated_permission_ids = [permission.pk for permission in deprecated_permissions]
        if deprecated_permission_ids:
            users_with_deprecated_permissions = (
                State.objects.filter(user__user_permissions__in=deprecated_permission_ids).distinct().count()
            )
            groups_with_deprecated_permissions = (
                Group.objects.filter(permissions__in=deprecated_permission_ids).distinct().count()
            )
            if not dry_run:
                for state in State.objects.filter(user__user_permissions__in=deprecated_permission_ids).distinct():
                    state.user.user_permissions.remove(*deprecated_permissions)
                for group in Group.objects.filter(permissions__in=deprecated_permission_ids).distinct():
                    group.permissions.remove(*deprecated_permissions)
                Permission.objects.filter(pk__in=deprecated_permission_ids).delete()

        permission_by_codename = {}
        created_permissions = 0
        for codename, name in PERMISSION_DEFINITIONS:
            permission, created = Permission.objects.get_or_create(
                content_type=state_content_type,
                codename=codename,
                defaults={"name": name},
            )
            if created:
                created_permissions += 1
            permission_by_codename[codename] = permission

        users_updated = 0
        permission_grants = 0
        for state in State.objects.select_related("user").iterator():
            mapped_codenames = {
                LEGACY_TO_CODENAME[legacy_permission]
                for legacy_permission in _to_permission_list(state.extra_user_permissions)
                if legacy_permission in LEGACY_TO_CODENAME
            }
            if not mapped_codenames:
                continue

            user = state.user
            pending_permissions = []
            for codename in mapped_codenames:
                permission = permission_by_codename.get(codename)
                if permission is None:
                    continue
                if not user.user_permissions.filter(pk=permission.pk).exists():
                    pending_permissions.append(permission)

            if not pending_permissions:
                continue

            users_updated += 1
            permission_grants += len(pending_permissions)
            if not dry_run:
                user.user_permissions.add(*pending_permissions)

        mode = "DRY-RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"[{mode}] Created permissions: {created_permissions}, "
                f"users updated: {users_updated}, grants added: {permission_grants}, "
                f"deprecated permissions removed from users: {users_with_deprecated_permissions}, "
                f"from groups: {groups_with_deprecated_permissions}"
            )
        )
