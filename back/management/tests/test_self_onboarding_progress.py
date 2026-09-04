from io import StringIO
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from management.models.courses import (
    ChapterQuizStep,
    Course,
    CourseChapter,
    UserCourseProgress,
    UserTypeAvailabilityChoices,
)
from management.models.profile import Profile
from management.models.state import State
from management.models.user import User
from management.self_onboarding_progress import progress_fields_from_legacy_state, self_onboarding_user_payload


class SelfOnboardingProgressMappingTests(TestCase):
    def test_finished_first_chapter_maps_to_second_chapter(self):
        state = State(
            self_onboarding_started=True,
            self_onboarding_completed=False,
            self_onboarding_step_id="self_onboarding_c1_q_1",
        )
        fields = progress_fields_from_legacy_state(
            state, ["self_onboarding_c1", "self_onboarding_c2", "self_onboarding_c3"]
        )
        self.assertEqual(fields["current_chapter_id"], "self_onboarding_c2")
        self.assertFalse(fields["completed"])

    def test_finished_last_chapter_maps_to_completed(self):
        state = State(
            self_onboarding_started=True,
            self_onboarding_completed=True,
            self_onboarding_step_id="self_onboarding_c3_q_1",
            self_onboarding_completed_at=timezone.now().date(),
        )
        fields = progress_fields_from_legacy_state(
            state, ["self_onboarding_c1", "self_onboarding_c2", "self_onboarding_c3"]
        )
        self.assertTrue(fields["completed"])
        self.assertEqual(fields["current_chapter_id"], "self_onboarding_c3")
        self.assertIsNotNone(fields["completed_at"])

    def test_user_payload_prefers_course_progress_over_state(self):
        course = Course.objects.create(
            slug=Course.SELF_ONBOARDING_SLUG,
            title="Onboarding",
            is_active=True,
            is_listed=False,
            available_to=UserTypeAvailabilityChoices.VOLUNTEER,
        )
        for i, chapter_id in enumerate(["self_onboarding_c1", "self_onboarding_c2", "self_onboarding_c3"]):
            CourseChapter.objects.create(
                course=course,
                chapter_id=chapter_id,
                order=i,
                title=chapter_id,
                video_url="https://example.com/video",
            )
        user = User.objects.create_user(
            email=f"payload-{uuid4()}@example.com",
            password="Test123!",
            first_name="Pay",
            last_name="Load",
        )
        user.state.self_onboarding_started = True
        user.state.self_onboarding_step_id = "self_onboarding_c1_q_1"
        user.state.save()
        UserCourseProgress.objects.create(
            user=user,
            course=course,
            current_chapter_id="self_onboarding_c2",
            current_step_index=0,
            completed=False,
        )

        payload = self_onboarding_user_payload(user)
        self.assertTrue(payload["selfOnboardingStarted"])
        self.assertEqual(payload["selfOnboardingStepId"], "self_onboarding_c2")
        self.assertAlmostEqual(payload["selfOnboardingProgress"], 1 / 3)


class BackfillSelfOnboardingCourseProgressTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            slug=Course.SELF_ONBOARDING_SLUG,
            title="Onboarding",
            is_active=True,
            is_listed=False,
            available_to=UserTypeAvailabilityChoices.VOLUNTEER,
        )
        for i, chapter_id in enumerate(["self_onboarding_c1", "self_onboarding_c2", "self_onboarding_c3"]):
            CourseChapter.objects.create(
                course=self.course,
                chapter_id=chapter_id,
                order=i,
                title=chapter_id,
                video_url="https://example.com/video",
            )
        self.user = User.objects.create_user(
            email=f"backfill-{uuid4()}@example.com",
            password="Test123!",
            first_name="Back",
            last_name="Fill",
        )
        self.user.profile.user_type = Profile.TypeChoices.VOLUNTEER
        self.user.profile.save(update_fields=["user_type"])
        self.user.state.self_onboarding_started = True
        self.user.state.self_onboarding_step_id = "self_onboarding_c1_q_1"
        self.user.state.save()

    def test_dry_run_does_not_write(self):
        out = StringIO()
        call_command("backfill_self_onboarding_course_progress", "--dry-run", stdout=out)
        self.assertFalse(UserCourseProgress.objects.filter(user=self.user, course=self.course).exists())
        self.assertIn("created=1", out.getvalue())

    def test_creates_progress_from_state_and_is_idempotent(self):
        call_command("backfill_self_onboarding_course_progress", stdout=StringIO())
        progress = UserCourseProgress.objects.get(user=self.user, course=self.course)
        self.assertEqual(progress.current_chapter_id, "self_onboarding_c2")
        self.assertFalse(progress.completed)

        call_command("backfill_self_onboarding_course_progress", stdout=StringIO())
        self.assertEqual(UserCourseProgress.objects.filter(user=self.user, course=self.course).count(), 1)


class SelfOnboardingStartHydrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.course = Course.objects.create(
            slug=Course.SELF_ONBOARDING_SLUG,
            title="Onboarding",
            is_active=True,
            is_listed=False,
            available_to=UserTypeAvailabilityChoices.VOLUNTEER,
        )
        for i, chapter_id in enumerate(["self_onboarding_c1", "self_onboarding_c2", "self_onboarding_c3"]):
            CourseChapter.objects.create(
                course=self.course,
                chapter_id=chapter_id,
                order=i,
                title=chapter_id,
                video_url="https://example.com/video",
            )
        self.user = User.objects.create_user(
            email=f"hydrate-{uuid4()}@example.com",
            password="Test123!",
            first_name="Hy",
            last_name="Drate",
        )
        self.user.profile.user_type = Profile.TypeChoices.VOLUNTEER
        self.user.profile.save(update_fields=["user_type"])
        self.user.state.self_onboarding_started = True
        self.user.state.self_onboarding_step_id = "self_onboarding_c2_q_1"
        self.user.state.save()
        self.client.force_authenticate(user=self.user)

    def test_start_copies_legacy_state_onto_new_progress(self):
        response = self.client.post(f"/api/courses/{Course.SELF_ONBOARDING_SLUG}/start/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["current_chapter_id"], "self_onboarding_c3")
        self.assertFalse(response.data["completed"])


class SelfOnboardingStepUpdateTests(TestCase):
    """POST /api/user/self_onboarding/update/ ranks against the course's actual chapters.

    The walkthrough reports a chapter's last quiz step, or the chapter id itself when the
    chapter is video-only. While the accepted ids were hardcoded, both a video-only chapter
    and any renamed or extra chapter were rejected — and the client swallows the error, so
    progress silently stopped being recorded.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email=f"walkthrough-{uuid4()}@example.com",
            password="Test123!",
            first_name="Walk",
            last_name="Through",
        )
        self.user.profile.user_type = Profile.TypeChoices.VOLUNTEER
        self.user.profile.save(update_fields=["user_type"])
        self.client.force_authenticate(user=self.user)

    def _course(self, chapter_ids, quiz_step_orders):
        """Course whose chapter ``chapter_ids[i]`` has ``quiz_step_orders[i]`` questions."""
        course = Course.objects.create(slug=Course.SELF_ONBOARDING_SLUG, title="Walkthrough", is_active=True)
        for idx, chapter_id in enumerate(chapter_ids):
            chapter = CourseChapter.objects.create(
                course=course,
                chapter_id=chapter_id,
                order=idx + 1,
                title=chapter_id,
                video_url="https://example.com/video",
            )
            for order in range(1, quiz_step_orders[idx] + 1):
                ChapterQuizStep.objects.create(
                    chapter=chapter,
                    order=order,
                    question=f"{chapter_id} q{order}",
                    answers=["Yes", "No"],
                    correct_answer="Yes",
                )
        return course

    def _report(self, marker):
        return self.client.post(f"/api/user/self_onboarding/update/?self_onboarding_step_id={marker}")

    def test_video_only_last_chapter_finishes_the_walkthrough(self):
        self._course(["self_onboarding_c1", "self_onboarding_c2", "self_onboarding_c3"], [1, 1, 0])

        first = self._report("self_onboarding_c1_q_1")
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.data["completed"])

        # A video-only chapter has no quiz step to report, so it reports its chapter id.
        last = self._report("self_onboarding_c3")
        self.assertEqual(last.status_code, 200)
        self.assertTrue(last.data["completed"])

        self.user.state.refresh_from_db()
        self.assertEqual(self.user.state.self_onboarding_step_id, "self_onboarding_c3")
        self.assertTrue(self.user.state.self_onboarding_completed)
        self.assertTrue(self.user.state.is_onboarded)
        self.assertEqual(self.user.state.searching_state, State.SearchingStateChoices.SEARCHING)

    def test_video_only_middle_chapter_records_progress_without_finishing(self):
        self._course(["self_onboarding_c1", "self_onboarding_c2", "self_onboarding_c3"], [1, 0, 1])

        response = self._report("self_onboarding_c2")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["completed"])

        self.user.state.refresh_from_db()
        self.assertEqual(self.user.state.self_onboarding_step_id, "self_onboarding_c2")
        self.assertTrue(self.user.state.self_onboarding_started)
        self.assertFalse(self.user.state.self_onboarding_completed)

    def test_renamed_chapters_and_later_quiz_steps_are_accepted(self):
        self._course(["intro", "how-it-works"], [2, 2])

        self.assertEqual(self._report("intro_q_2").status_code, 200)
        last = self._report("how-it-works_q_2")
        self.assertEqual(last.status_code, 200)
        self.assertTrue(last.data["completed"])

    def test_legacy_step_ids_still_work_without_a_course_row(self):
        self.assertEqual(self._report("self_onboarding_c1_q_1").status_code, 200)
        last = self._report("self_onboarding_c3_q_1")
        self.assertEqual(last.status_code, 200)
        self.assertTrue(last.data["completed"])

    def test_unknown_marker_is_still_rejected(self):
        self._course(["self_onboarding_c1"], [1])
        self.assertEqual(self._report("not-a-chapter").status_code, 400)
