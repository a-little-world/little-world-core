from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
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
from management.permissions import ManagementPermission


class CourseProgressApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        content_type = ContentType.objects.get(app_label="management", model="state")
        Permission.objects.get_or_create(
            codename=ManagementPermission.USE_RANDOM_CALLS.codename,
            content_type=content_type,
            defaults={"name": ManagementPermission.USE_RANDOM_CALLS.codename},
        )

        self.onboarding = Course.objects.create(
            slug=Course.SELF_ONBOARDING_SLUG,
            title="Einführungs-Rundgang",
            is_active=True,
            is_listed=False,
            available_to=UserTypeAvailabilityChoices.VOLUNTEER,
        )
        self.training = Course.objects.create(
            slug="example-training",
            title="Example Training",
            is_active=True,
            is_listed=True,
            available_to=UserTypeAvailabilityChoices.ALL,
        )

        self.volunteer = self._create_user("volunteer", Profile.TypeChoices.VOLUNTEER)
        self.learner = self._create_user("learner", Profile.TypeChoices.LEARNER)

    def _create_user(self, prefix: str, user_type: str) -> User:
        user = User.objects.create_user(
            email=f"{prefix}-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name="User",
        )
        user.profile.user_type = user_type
        user.profile.save(update_fields=["user_type"])
        return user

    def test_list_excludes_self_onboarding_even_when_active(self):
        self.client.force_authenticate(user=self.volunteer)
        response = self.client.get("/api/courses/")
        self.assertEqual(response.status_code, 200)
        slugs = [course["slug"] for course in response.data]
        self.assertIn(self.training.slug, slugs)
        self.assertNotIn(Course.SELF_ONBOARDING_SLUG, slugs)

    def test_volunteer_can_fetch_and_start_self_onboarding_via_generic_endpoints(self):
        self.client.force_authenticate(user=self.volunteer)

        detail = self.client.get(f"/api/courses/{Course.SELF_ONBOARDING_SLUG}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["slug"], Course.SELF_ONBOARDING_SLUG)

        start = self.client.post(f"/api/courses/{Course.SELF_ONBOARDING_SLUG}/start/")
        self.assertEqual(start.status_code, 200)
        self.assertFalse(start.data["completed"])
        self.assertTrue(UserCourseProgress.objects.filter(user=self.volunteer, course=self.onboarding).exists())

        progress = self.client.patch(
            f"/api/courses/{Course.SELF_ONBOARDING_SLUG}/progress/",
            {"current_chapter_id": "self_onboarding_c1", "current_step_index": 1},
            format="json",
        )
        self.assertEqual(progress.status_code, 200)
        self.assertEqual(progress.data["current_chapter_id"], "self_onboarding_c1")

    def test_learner_cannot_take_self_onboarding_course(self):
        self.client.force_authenticate(user=self.learner)
        self.assertEqual(self.client.get(f"/api/courses/{Course.SELF_ONBOARDING_SLUG}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/courses/{Course.SELF_ONBOARDING_SLUG}/start/").status_code, 404)

    @patch("management.tasks.send_email_background")
    def test_completing_self_onboarding_applies_matching_side_effects(self, mock_send_email):
        self.client.force_authenticate(user=self.volunteer)
        self.client.post(f"/api/courses/{Course.SELF_ONBOARDING_SLUG}/start/")

        response = self.client.post(f"/api/courses/{Course.SELF_ONBOARDING_SLUG}/complete/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["completed"])

        self.volunteer.state.refresh_from_db()
        self.volunteer.refresh_from_db()
        self.assertTrue(self.volunteer.state.is_onboarded)
        self.assertTrue(self.volunteer.state.self_onboarding_completed)
        self.assertTrue(self.volunteer.state.self_onboarding_started)
        self.assertEqual(self.volunteer.state.searching_state, State.SearchingStateChoices.SEARCHING)
        self.assertTrue(self.volunteer.state.attended_auto_email_u071_send)
        self.assertTrue(self.volunteer.has_perm(ManagementPermission.USE_RANDOM_CALLS))
        mock_send_email.delay.assert_called_once_with(
            "automatic-emails-u071",
            user_id=self.volunteer.id,
        )

        mock_send_email.delay.reset_mock()
        second = self.client.post(f"/api/courses/{Course.SELF_ONBOARDING_SLUG}/complete/")
        self.assertEqual(second.status_code, 200)
        mock_send_email.delay.assert_not_called()

    @patch("management.tasks.send_email_background")
    def test_completing_a_regular_course_does_not_onboard(self, mock_send_email):
        self.client.force_authenticate(user=self.volunteer)
        self.client.post(f"/api/courses/{self.training.slug}/start/")

        response = self.client.post(f"/api/courses/{self.training.slug}/complete/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["completed"])

        self.volunteer.state.refresh_from_db()
        self.assertFalse(self.volunteer.state.is_onboarded)
        self.assertFalse(self.volunteer.state.self_onboarding_completed)
        self.assertEqual(self.volunteer.state.searching_state, State.SearchingStateChoices.IDLE)
        self.assertFalse(self.volunteer.has_perm(ManagementPermission.USE_RANDOM_CALLS))
        mock_send_email.delay.assert_not_called()


class CourseStatsFunnelTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.course = Course.objects.create(
            slug="stats-course",
            title="Stats Course",
            is_active=True,
            is_listed=True,
            available_to=UserTypeAvailabilityChoices.ALL,
        )
        for i, chapter_id in enumerate(["c1", "c2", "c3"]):
            CourseChapter.objects.create(
                course=self.course,
                chapter_id=chapter_id,
                order=i,
                title=chapter_id,
                video_url="https://example.com/video",
            )
        self.staff = User.objects.create_user(
            email=f"stats-staff-{uuid4()}@example.com",
            password="Test123!",
            first_name="Stats",
            last_name="Staff",
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        self.client.force_authenticate(user=self.staff)

    def _add_progress(self, *, current_chapter_id: str, completed: bool = False):
        user = User.objects.create_user(
            email=f"stats-{uuid4()}@example.com",
            password="Test123!",
            first_name="Funnel",
            last_name="User",
        )
        UserCourseProgress.objects.create(
            user=user,
            course=self.course,
            current_chapter_id=current_chapter_id,
            completed=completed,
        )

    def test_drop_off_is_share_still_on_this_chapter(self):
        for _ in range(2):
            self._add_progress(current_chapter_id="c1")
        for _ in range(3):
            self._add_progress(current_chapter_id="c2")
        self._add_progress(current_chapter_id="c3")
        for _ in range(10):
            self._add_progress(current_chapter_id="c3", completed=True)

        response = self.client.get(f"/api/admin/courses/{self.course.slug}/stats/")
        self.assertEqual(response.status_code, 200)
        funnel = response.data["chapter_funnel"]
        self.assertEqual([row["currently_here"] for row in funnel], [2, 3, 1])
        self.assertEqual([row["reached"] for row in funnel], [16, 14, 11])
        # 2/16, 3/14, 1/11 — stalls belong on the chapter people are sitting on
        self.assertEqual([row["drop_off_pct"] for row in funnel], [12.5, 21.4, 9.1])


class AdminCourseVideoOnlyChapterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email=f"course-admin-{uuid4()}@example.com",
            password="Test123!",
            first_name="Course",
            last_name="Admin",
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        self.client.force_authenticate(user=self.staff)

    def test_create_and_update_chapter_without_quiz_steps(self):
        create = self.client.post(
            "/api/admin/courses/",
            {
                "title": "Video Only",
                "slug": "video-only",
                "description": "",
                "is_active": True,
                "is_listed": True,
                "available_to": UserTypeAvailabilityChoices.ALL,
                "chapters": [
                    {
                        "chapter_id": "watch-intro",
                        "order": 1,
                        "available_to": UserTypeAvailabilityChoices.ALL,
                        "title": "Watch intro",
                        "description": "",
                        "video_url": "https://example.com/intro",
                        "video_title": "Intro",
                        "completed_title": "",
                        "completed_description": "",
                        "completed_additional_text": "",
                        "completed_cta_label": "",
                        "quiz_steps": [],
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        self.assertEqual(create.data["chapters"][0]["quiz_steps"], [])
        self.assertEqual(ChapterQuizStep.objects.count(), 0)

        volunteer = User.objects.create_user(
            email=f"video-learner-{uuid4()}@example.com",
            password="Test123!",
            first_name="Video",
            last_name="Learner",
        )
        volunteer.profile.user_type = Profile.TypeChoices.VOLUNTEER
        volunteer.profile.save(update_fields=["user_type"])
        learner_client = APIClient()
        learner_client.force_authenticate(user=volunteer)
        detail = learner_client.get("/api/courses/video-only/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["chapters"][0]["quiz_steps"], [])

        update = self.client.put(
            "/api/admin/courses/video-only/",
            {
                "title": "Video Only",
                "slug": "video-only",
                "description": "Updated",
                "is_active": True,
                "is_listed": True,
                "available_to": UserTypeAvailabilityChoices.ALL,
                "chapters": [
                    {
                        "chapter_id": "watch-intro",
                        "order": 1,
                        "available_to": UserTypeAvailabilityChoices.ALL,
                        "title": "Watch intro",
                        "description": "",
                        "video_url": "https://example.com/intro",
                        "video_title": "Intro",
                        "completed_title": "",
                        "completed_description": "",
                        "completed_additional_text": "",
                        "completed_cta_label": "",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data["chapters"][0]["quiz_steps"], [])
        self.assertEqual(ChapterQuizStep.objects.count(), 0)
