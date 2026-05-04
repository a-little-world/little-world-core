from collections import defaultdict

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from management.models.state import State
from management.models.user import User

# Legacy values from state.extra_user_permissions (includes deprecated values for migration audits).
LEGACY_PERMISSION_VALUES = [
    "view-api-schema",
    "view-database-schema",
    "use-autologin-api",
    "view-docs",
    "view-email-templates",
    "view-stats",
    "matching-user",
    "uncensored-admin-matcher",
    "use-beta-random-call",
    "use-random-calls",
]

# Django permission codenames anchored on management.state (includes deprecated values for migration audits).
STATE_PERMISSION_CODENAMES = [
    "view_api_schema",
    "view_database_schema",
    "use_autologin_api",
    "view_docs",
    "view_email_templates",
    "view_stats",
    "matching_user",
    "uncensored_admin_matcher",
    "use_beta_random_call",
    "use_random_calls",
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
    help = (
        "Print detailed overview of legacy state.extra_user_permissions and "
        "Django state permissions, including user id/email per permission."
    )

    def handle(self, *args, **options):
        self._print_legacy_overview()
        self.stdout.write("")
        self._print_django_overview()

    def _print_legacy_overview(self):
        self.stdout.write(self.style.MIGRATE_HEADING("=== Legacy state.extra_user_permissions ==="))

        users_by_permission = defaultdict(list)
        unknown_legacy_values = defaultdict(list)
        users_with_any_legacy_permission = set()

        tracked_values = set(LEGACY_PERMISSION_VALUES)
        for state in State.objects.select_related("user").iterator():
            permissions = _to_permission_list(state.extra_user_permissions)
            if not permissions:
                continue

            user = state.user
            users_with_any_legacy_permission.add(user.pk)
            for permission_value in permissions:
                if permission_value in tracked_values:
                    users_by_permission[permission_value].append(user)
                else:
                    unknown_legacy_values[permission_value].append(user)

        self.stdout.write(f"Users with any legacy permission value: {len(users_with_any_legacy_permission)}")
        self.stdout.write("")

        for permission_value in LEGACY_PERMISSION_VALUES:
            users = self._dedupe_and_sort_users(users_by_permission.get(permission_value, []))
            self.stdout.write(f"- {permission_value}: {len(users)} user(s)")
            self._print_user_lines(users)

        if unknown_legacy_values:
            self.stdout.write("")
            self.stdout.write("Unknown legacy values found (not in tracked list):")
            for permission_value in sorted(unknown_legacy_values):
                users = self._dedupe_and_sort_users(unknown_legacy_values[permission_value])
                self.stdout.write(f"- {permission_value}: {len(users)} user(s)")
                self._print_user_lines(users)

    def _print_django_overview(self):
        self.stdout.write(self.style.MIGRATE_HEADING("=== Django permissions (management.state) ==="))

        state_content_type, _ = ContentType.objects.get_or_create(app_label="management", model="state")

        users_with_any_state_permission = set()
        for codename in STATE_PERMISSION_CODENAMES:
            permission = Permission.objects.filter(content_type=state_content_type, codename=codename).first()
            if permission is None:
                self.stdout.write(f"- management.{codename}: 0 user(s) [permission row missing]")
                continue

            users = list(User.objects.filter(user_permissions=permission).distinct().order_by("id"))
            for user in users:
                users_with_any_state_permission.add(user.pk)

            self.stdout.write(f"- management.{codename}: {len(users)} user(s)")
            self._print_user_lines(users)

        self.stdout.write("")
        self.stdout.write(f"Users with any tracked Django state permission: {len(users_with_any_state_permission)}")

    def _print_user_lines(self, users):
        if not users:
            self.stdout.write("  (none)")
            return
        for user in users:
            self.stdout.write(f"  - id={user.pk} email={user.email}")

    def _dedupe_and_sort_users(self, users):
        by_pk = {user.pk: user for user in users}
        return [by_pk[pk] for pk in sorted(by_pk.keys())]
