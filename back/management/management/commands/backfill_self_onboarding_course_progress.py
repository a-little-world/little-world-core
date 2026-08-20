from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from management.models.courses import Course, UserCourseProgress
from management.models.state import State
from management.self_onboarding_progress import (
    hydrate_progress_from_legacy_state,
    legacy_state_has_progress,
)


class Command(BaseCommand):
    help = (
        "Create UserCourseProgress rows for the self-onboarding course from "
        "legacy State.self_onboarding_* fields. Idempotent: existing progress rows are left unchanged. "
        "Run once on production after deploying course-progress walkthrough."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of state rows to process per batch.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview how many progress rows would be created without writing.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        try:
            course = Course.objects.get(slug=Course.SELF_ONBOARDING_SLUG)
        except Course.DoesNotExist as exc:
            raise CommandError(
                f'Course "{Course.SELF_ONBOARDING_SLUG}" does not exist. Create it before backfilling.'
            ) from exc

        queryset = (
            State.objects.filter(
                Q(self_onboarding_started=True) | Q(self_onboarding_completed=True) | ~Q(self_onboarding_step_id="")
            )
            .select_related("user")
            .order_by("id")
        )
        total = queryset.count()
        created = 0
        skipped_existing = 0
        skipped_empty = 0
        processed = 0

        existing_user_ids = set(UserCourseProgress.objects.filter(course=course).values_list("user_id", flat=True))

        for state in queryset.iterator(chunk_size=batch_size):
            processed += 1
            if not legacy_state_has_progress(state):
                skipped_empty += 1
                continue
            if state.user_id in existing_user_ids:
                skipped_existing += 1
                continue

            created += 1
            if not dry_run:
                with transaction.atomic():
                    progress = UserCourseProgress.objects.create(user_id=state.user_id, course=course)
                    hydrate_progress_from_legacy_state(progress, state)
                existing_user_ids.add(state.user_id)

            if processed % batch_size == 0:
                self.stdout.write(f"Processed {processed}/{total} state rows")

        mode = "DRY RUN" if dry_run else "DONE"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: processed={processed} created={created} "
                f"skipped_existing={skipped_existing} skipped_empty={skipped_empty}"
            )
        )
