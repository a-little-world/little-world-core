from django.core.management.base import BaseCommand

from management.models.management_access_grant import ManagementAccessGrant
from management.models.state import State


class Command(BaseCommand):
    help = (
        "Backfill ManagementAccessGrant rows from legacy State.managed_users to preserve "
        "current manager->managed-user access."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without writing updates.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing ManagementAccessGrant rows before backfilling.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        reset = options["reset"]

        if reset:
            existing_count = ManagementAccessGrant.objects.count()
            if not dry_run:
                ManagementAccessGrant.objects.all().delete()
            self.stdout.write(f"Reset existing access grants: {existing_count}")

        # TODO: deprecated - remove legacy state.managed_users dependency after full ACL cutover.
        through_model = State.managed_users.through
        state_to_manager_user_id = dict(State.objects.values_list("id", "user_id"))
        relationships = list(through_model.objects.values_list("state_id", "user_id"))

        created = 0
        reactivated = 0
        unchanged = 0
        skipped_missing_manager = 0

        for state_id, managed_user_id in relationships:
            manager_user_id = state_to_manager_user_id.get(state_id)
            if manager_user_id is None:
                skipped_missing_manager += 1
                continue

            if dry_run:
                existing = ManagementAccessGrant.objects.filter(
                    manager_id=manager_user_id,
                    managed_user_id=managed_user_id,
                ).first()
                if existing is None:
                    created += 1
                elif not existing.is_active:
                    reactivated += 1
                else:
                    unchanged += 1
                continue

            grant, was_created = ManagementAccessGrant.objects.get_or_create(
                manager_id=manager_user_id,
                managed_user_id=managed_user_id,
                defaults={"is_active": True},
            )
            if was_created:
                created += 1
                continue

            if not grant.is_active:
                grant.is_active = True
                grant.save(update_fields=["is_active", "updated_at"])
                reactivated += 1
            else:
                unchanged += 1

        mode = "DRY-RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"[{mode}] legacy relationships={len(relationships)}, "
                f"created={created}, reactivated={reactivated}, unchanged={unchanged}, "
                f"skipped_missing_manager={skipped_missing_manager}"
            )
        )
