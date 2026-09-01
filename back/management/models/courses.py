from django.db import models, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework import serializers


class UserTypeAvailabilityChoices(models.TextChoices):
    ALL = "all", "All"
    LEARNER = "learner", "Learner"
    VOLUNTEER = "volunteer", "Volunteer"


class Course(models.Model):
    SELF_ONBOARDING_SLUG = "self-onboarding"

    slug = models.SlugField(max_length=128, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="courses/", null=True, blank=True)
    is_active = models.BooleanField(default=False)
    is_listed = models.BooleanField(
        default=True,
        help_text="Show this course in public listings (e.g. the Trainings page). "
        "Disable for internal-only courses such as onboarding walkthroughs.",
    )
    available_to = models.CharField(
        max_length=16,
        choices=UserTypeAvailabilityChoices.choices,
        default=UserTypeAvailabilityChoices.ALL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "management"

    def __str__(self):
        return self.title

    def is_available_to_user(self, user) -> bool:
        user_type = user.profile.user_type
        return self.available_to in (UserTypeAvailabilityChoices.ALL, user_type)

    def get_chapters_for_user(self, user):
        user_type = user.profile.user_type
        return self.chapters.filter(
            Q(available_to=UserTypeAvailabilityChoices.ALL) | Q(available_to=user_type)
        ).order_by("order")

    def get_chapters_for_course_audience(self):
        """
        Chapters as seen by the course's target audience (not the requesting user).
        Used for staff preview so matching users with a different profile type still
        see volunteer-only onboarding content, etc.
        """
        # When the course is for all types, include every chapter (including
        # learner- or volunteer-only chapters). The filter below would only match
        # chapters with available_to=ALL, omitting type-restricted chapters.
        if self.available_to == UserTypeAvailabilityChoices.ALL:
            return self.chapters.order_by("order")
        return self.chapters.filter(
            Q(available_to=UserTypeAvailabilityChoices.ALL) | Q(available_to=self.available_to)
        ).order_by("order")

    @classmethod
    def get_available_for_user(cls, user):
        user_type = user.profile.user_type
        return cls.objects.filter(is_active=True).filter(
            Q(available_to=UserTypeAvailabilityChoices.ALL) | Q(available_to=user_type)
        )


class CourseChapter(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="chapters")
    chapter_id = models.CharField(max_length=128)
    order = models.PositiveIntegerField()
    available_to = models.CharField(
        max_length=16,
        choices=UserTypeAvailabilityChoices.choices,
        default=UserTypeAvailabilityChoices.ALL,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    video_url = models.URLField()
    video_title = models.CharField(max_length=255, blank=True, default="")
    completed_title = models.CharField(max_length=255, blank=True, default="")
    completed_description = models.TextField(blank=True, default="")
    completed_additional_text = models.TextField(blank=True, default="")
    completed_cta_label = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        app_label = "management"
        unique_together = ("course", "chapter_id")
        ordering = ["order"]

    def __str__(self):
        return f"{self.course.title} — {self.title}"


class ChapterQuizStep(models.Model):
    chapter = models.ForeignKey(CourseChapter, on_delete=models.CASCADE, related_name="quiz_steps")
    order = models.PositiveIntegerField()
    question = models.TextField()
    answers = models.JSONField(default=list, help_text='List of answer strings, e.g. ["Yes", "No", "Maybe"]')
    correct_answer = models.CharField(max_length=512)

    class Meta:
        app_label = "management"
        ordering = ["order"]

    def __str__(self):
        return f"{self.chapter} — Q{self.order}"


class UserCourseProgress(models.Model):
    user = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="course_progress")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="user_progress")
    started_at = models.DateTimeField(auto_now_add=True)
    current_chapter_id = models.CharField(max_length=128, blank=True, default="")
    current_step_index = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True, default=None)

    class Meta:
        app_label = "management"
        unique_together = ("user", "course")

    def __str__(self):
        return f"{self.user} — {self.course.title}"

    @classmethod
    def exists_for_user(cls, *, slug: str, completed: bool | None = None, **filters):
        """Exists() subquery against the outer User.pk. Safe to OR into a User filter."""
        qs = cls.objects.filter(user_id=OuterRef("pk"), course__slug=slug, **filters)
        if completed is not None:
            qs = qs.filter(completed=completed)
        return Exists(qs)

    def progress_fraction(self) -> float:
        if self.completed:
            return 1.0
        chapter_ids = list(self.course.chapters.order_by("order").values_list("chapter_id", flat=True))
        n = len(chapter_ids)
        if n == 0 or not self.current_chapter_id:
            return 0.0
        try:
            idx = chapter_ids.index(self.current_chapter_id)
        except ValueError:
            return 0.0
        return max(0.0, min(1.0, idx / float(n)))

    def mark_completed(self):
        if self.completed:
            return

        with transaction.atomic():
            self.completed = True
            self.completed_at = timezone.now()
            self.save(update_fields=["completed", "completed_at"])
            if self.course.slug == Course.SELF_ONBOARDING_SLUG:
                self._apply_self_onboarding_completion()

    def _apply_self_onboarding_completion(self):
        """Matching-eligibility side effects. Only called for the self-onboarding course.

        The eligibility half runs only for a user who was not onboarded yet. The
        walkthrough route carries no ``is_onboarded`` guard, so a volunteer onboarded by
        an onboarding call can reach and finish the course — and turning searching back on
        under them would drop someone who deliberately paused back into the matching pool
        with no indication. Recording the walkthrough as done is always safe; declaring
        them freshly available to match is not.
        """
        from management.models.state import State
        from management.permissions import ManagementPermission
        from management.tasks import send_email_background

        user = self.user
        state = user.state
        was_onboarded = state.is_onboarded
        already_sent_u071 = state.attended_auto_email_u071_send

        state.self_onboarding_started = True
        state.self_onboarding_completed = True
        state.self_onboarding_completed_at = timezone.now()
        state.is_onboarded = True
        send_u071 = not was_onboarded and not already_sent_u071
        if not was_onboarded:
            state.searching_state = State.SearchingStateChoices.SEARCHING
        if send_u071:
            state.attended_auto_email_u071_send = True
            state.attended_auto_email_u071_send_at = timezone.now()
        state.save()

        if not was_onboarded:
            user.grant_permission(ManagementPermission.USE_RANDOM_CALLS)
        if send_u071:
            send_email_background.delay("automatic-emails-u071", user_id=user.id)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class ChapterQuizStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChapterQuizStep
        fields = ["order", "question", "answers", "correct_answer"]


class CourseChapterSerializer(serializers.ModelSerializer):
    quiz_steps = ChapterQuizStepSerializer(many=True, read_only=True)

    class Meta:
        model = CourseChapter
        fields = [
            "chapter_id",
            "order",
            "title",
            "description",
            "video_url",
            "video_title",
            "completed_title",
            "completed_description",
            "completed_additional_text",
            "completed_cta_label",
            "quiz_steps",
        ]


class CourseListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["slug", "image", "title", "description", "available_to"]


class CourseDetailSerializer(serializers.ModelSerializer):
    chapters = serializers.SerializerMethodField()

    def get_chapters(self, obj):
        if self.context.get("staff_preview"):
            chapters = obj.get_chapters_for_course_audience()
        else:
            request = self.context.get("request")
            if request is not None:
                chapters = obj.get_chapters_for_user(request.user)
            else:
                chapters = obj.chapters.order_by("order")
        return CourseChapterSerializer(chapters, many=True).data

    class Meta:
        model = Course
        fields = ["slug", "image", "title", "description", "chapters"]


class UserCourseProgressSerializer(serializers.ModelSerializer):
    course_slug = serializers.CharField(source="course.slug", read_only=True)

    class Meta:
        model = UserCourseProgress
        fields = [
            "course_slug",
            "started_at",
            "current_chapter_id",
            "current_step_index",
            "completed",
            "completed_at",
        ]


class CourseProgressUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCourseProgress
        fields = ["current_chapter_id", "current_step_index"]
