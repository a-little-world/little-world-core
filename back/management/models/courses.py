from django.db import models
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers


class UserTypeAvailabilityChoices(models.TextChoices):
    ALL = "all", "All"
    LEARNER = "learner", "Learner"
    VOLUNTEER = "volunteer", "Volunteer"


class Course(models.Model):
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

    def get_chapters_for_user(self, user):
        user_type = user.profile.user_type
        return self.chapters.filter(
            Q(available_to=UserTypeAvailabilityChoices.ALL) | Q(available_to=user_type)
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

    def mark_completed(self):
        if not self.completed:
            self.completed = True
            self.completed_at = timezone.now()
            self.save()


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
        request = self.context.get("request")
        if request:
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
