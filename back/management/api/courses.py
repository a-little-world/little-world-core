from django.db.models import Avg, DurationField, ExpressionWrapper, F
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.helpers.detailed_pagination import DetailedPagination, get_paginated_format_v2
from management.models.courses import (
    ChapterQuizStep,
    Course,
    CourseChapter,
    CourseDetailSerializer,
    CourseListSerializer,
    CourseProgressUpdateSerializer,
    UserCourseProgress,
    UserCourseProgressSerializer,
)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def course_list(request):
    """
    Returns all active courses available to the current user, filtered by their user type.
    """
    courses = Course.get_available_for_user(request.user).filter(is_listed=True)
    return Response(CourseListSerializer(courses, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def course_detail(request, slug: str):
    """
    Returns full course detail. Chapters are filtered and ordered for the requesting user's type.
    Staff users may pass ?preview=1 to view inactive/restricted courses without publishing them.
    """
    from management.permissions import ManagementPermission

    is_preview = (
        request.query_params.get("preview") == "1"
        and request.user.is_authenticated
        and request.user.has_perm(ManagementPermission.MATCHING_USER)
    )

    if is_preview:
        course = get_object_or_404(Course, slug=slug)
    else:
        course = get_object_or_404(Course, slug=slug, is_active=True)
        user_type = request.user.profile.user_type
        if course.available_to not in ("all", user_type):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(CourseDetailSerializer(course, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def course_start(request, slug: str):
    """
    Starts a course for the current user. Idempotent — returns existing progress if already started.
    """
    course = get_object_or_404(Course, slug=slug, is_active=True)

    user_type = request.user.profile.user_type
    if course.available_to not in ("all", user_type):
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    progress, _ = UserCourseProgress.objects.get_or_create(
        user=request.user,
        course=course,
    )
    return Response(UserCourseProgressSerializer(progress).data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def course_progress_update(request, slug: str):
    """
    Updates the user's progress within a course.
    Accepts: { "current_chapter_id": str, "current_step_index": int }
    When advancing to a new chapter, pass current_step_index: 0.
    """
    course = get_object_or_404(Course, slug=slug, is_active=True)
    progress = get_object_or_404(UserCourseProgress, user=request.user, course=course)

    if progress.completed:
        return Response({"detail": "Course already completed."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = CourseProgressUpdateSerializer(progress, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        progress.refresh_from_db()
        return Response(UserCourseProgressSerializer(progress).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def course_complete(request, slug: str):
    """
    Marks a course as completed for the current user. Idempotent.
    """
    course = get_object_or_404(Course, slug=slug, is_active=True)
    progress = get_object_or_404(UserCourseProgress, user=request.user, course=course)

    progress.mark_completed()
    return Response(UserCourseProgressSerializer(progress).data)


# ---------------------------------------------------------------------------
# Admin stats
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_course_stats(request, slug: str):
    """
    Returns engagement stats for a course.
    Optional query params: start_date (YYYY-MM-DD), end_date (YYYY-MM-DD) — filter by started_at.
    """
    course = get_object_or_404(Course, slug=slug)

    progress_qs = UserCourseProgress.objects.filter(course=course)
    if start_date := request.query_params.get("start_date"):
        progress_qs = progress_qs.filter(started_at__date__gte=start_date)
    if end_date := request.query_params.get("end_date"):
        progress_qs = progress_qs.filter(started_at__date__lte=end_date)

    total_started = progress_qs.count()
    total_completed = progress_qs.filter(completed=True).count()
    completion_rate = round(total_completed / total_started * 100, 1) if total_started else 0.0

    # Average days to complete (completed records only)
    avg_days = None
    avg_result = (
        progress_qs.filter(completed=True, completed_at__isnull=False)
        .annotate(duration=ExpressionWrapper(F("completed_at") - F("started_at"), output_field=DurationField()))
        .aggregate(avg=Avg("duration"))["avg"]
    )
    if avg_result is not None:
        avg_days = round(avg_result.total_seconds() / 86400, 1)

    # Chapter funnel — one pass over all progress rows, then aggregate per chapter
    chapters = list(course.chapters.order_by("order"))
    chapter_id_to_index = {ch.chapter_id: i for i, ch in enumerate(chapters)}
    n = len(chapters)

    all_rows = list(progress_qs.values("current_chapter_id", "completed"))

    reached_counts = [0] * n
    currently_here_counts = [0] * n

    for row in all_rows:
        if row["completed"]:
            for j in range(n):
                reached_counts[j] += 1
        else:
            cid = row["current_chapter_id"]
            # Empty string → user started but hasn't advanced past chapter 0 yet
            current_idx = 0 if cid == "" else chapter_id_to_index.get(cid)
            if current_idx is not None:
                for j in range(current_idx + 1):
                    reached_counts[j] += 1
                currently_here_counts[current_idx] += 1

    chapter_funnel = []
    for i, chapter in enumerate(chapters):
        prev_reached = chapter_funnel[i - 1]["reached"] if i > 0 else total_started
        drop_off_pct = round((prev_reached - reached_counts[i]) / prev_reached * 100, 1) if prev_reached > 0 else 0.0
        chapter_funnel.append(
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "order": chapter.order,
                "step_count": chapter.quiz_steps.count(),
                "reached": reached_counts[i],
                "currently_here": currently_here_counts[i],
                "drop_off_pct": drop_off_pct,
            }
        )

    return Response(
        {
            "course_slug": slug,
            "course_title": course.title,
            "total_started": total_started,
            "total_completed": total_completed,
            "completion_rate": completion_rate,
            "avg_days_to_complete": avg_days,
            "chapter_funnel": chapter_funnel,
        }
    )


# ---------------------------------------------------------------------------
# Admin serializers
# ---------------------------------------------------------------------------


class AdminChapterQuizStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChapterQuizStep
        fields = ["order", "question", "answers", "correct_answer"]


class AdminCourseChapterSerializer(serializers.ModelSerializer):
    quiz_steps = AdminChapterQuizStepSerializer(many=True, required=False, default=list)

    class Meta:
        model = CourseChapter
        fields = [
            "chapter_id",
            "order",
            "available_to",
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


class AdminCourseListSerializer(serializers.ModelSerializer):
    chapter_count = serializers.SerializerMethodField()

    def get_chapter_count(self, obj):
        return obj.chapters.count()

    class Meta:
        model = Course
        fields = [
            "id",
            "slug",
            "title",
            "description",
            "image",
            "is_active",
            "is_listed",
            "available_to",
            "created_at",
            "updated_at",
            "chapter_count",
        ]


class AdminCourseSerializer(serializers.ModelSerializer):
    chapters = AdminCourseChapterSerializer(many=True, required=False, default=list)
    # image is read-only here; use the dedicated image endpoint to upload/remove.
    image = serializers.ImageField(read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "slug",
            "title",
            "description",
            "image",
            "is_active",
            "is_listed",
            "available_to",
            "created_at",
            "updated_at",
            "chapters",
        ]

    def create(self, validated_data):
        chapters_data = validated_data.pop("chapters", [])
        course = Course.objects.create(**validated_data)
        self._sync_chapters(course, chapters_data)
        return course

    def update(self, instance, validated_data):
        chapters_data = validated_data.pop("chapters", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if chapters_data is not None:
            self._sync_chapters(instance, chapters_data)
        return instance

    def _sync_chapters(self, course, chapters_data):
        submitted_chapter_ids = {c["chapter_id"] for c in chapters_data}
        course.chapters.exclude(chapter_id__in=submitted_chapter_ids).delete()

        for chapter_data in chapters_data:
            quiz_steps_data = chapter_data.pop("quiz_steps", [])
            chapter, _ = CourseChapter.objects.update_or_create(
                course=course,
                chapter_id=chapter_data["chapter_id"],
                defaults=chapter_data,
            )
            chapter.quiz_steps.all().delete()
            for step_data in quiz_steps_data:
                ChapterQuizStep.objects.create(chapter=chapter, **step_data)


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_course_image(request, slug: str):
    """
    PATCH  — upload a course image (multipart/form-data with an 'image' file field).
    DELETE — remove the course image.
    Returns the updated course (AdminCourseSerializer).
    """
    course = get_object_or_404(Course, slug=slug)

    if request.method == "DELETE":
        if course.image:
            course.image.delete(save=False)
        course.image = None
        course.save(update_fields=["image"])
        return Response(AdminCourseSerializer(course).data)

    if "image" not in request.FILES:
        return Response(
            {"detail": "Provide an 'image' file."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if course.image:
        course.image.delete(save=False)
    course.image = request.FILES["image"]
    course.save(update_fields=["image"])
    return Response(AdminCourseSerializer(course).data)


@api_view(["GET", "POST"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_course_list(request):
    """
    GET  — list all courses (including inactive). Supports page and page_size query params.
    POST — create a new course.
    """
    if request.method == "GET":
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", DetailedPagination.page_size))
        page_size = min(max(page_size, 1), DetailedPagination.max_page_size)

        courses_qs = Course.objects.all().order_by("-created_at")
        paginated = get_paginated_format_v2(courses_qs, page_size, page)
        paginated["results"] = AdminCourseListSerializer(paginated["results"], many=True).data
        return Response(paginated)

    serializer = AdminCourseSerializer(data=request.data)
    if serializer.is_valid():
        course = serializer.save()
        return Response(AdminCourseSerializer(course).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_course_detail(request, slug: str):
    """
    GET    — full course detail with chapters + quiz steps.
    PUT    — wholesale update of course + chapters (syncs by chapter_id).
    DELETE — delete course.
    """
    course = get_object_or_404(Course, slug=slug)

    if request.method == "GET":
        return Response(AdminCourseSerializer(course).data)

    if request.method == "DELETE":
        course.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = AdminCourseSerializer(course, data=request.data)
    if serializer.is_valid():
        updated = serializer.save()
        return Response(AdminCourseSerializer(updated).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


api_urls = [
    # User-facing
    path("api/courses/", course_list, name="course_list"),
    path("api/courses/<slug:slug>/", course_detail, name="course_detail"),
    path("api/courses/<slug:slug>/start/", course_start, name="course_start"),
    path("api/courses/<slug:slug>/progress/", course_progress_update, name="course_progress_update"),
    path("api/courses/<slug:slug>/complete/", course_complete, name="course_complete"),
    # Admin
    path("api/admin/courses/", admin_course_list, name="admin_course_list"),
    path("api/admin/courses/<slug:slug>/", admin_course_detail, name="admin_course_detail"),
    path("api/admin/courses/<slug:slug>/image/", admin_course_image, name="admin_course_image"),
    path("api/admin/courses/<slug:slug>/stats/", admin_course_stats, name="admin_course_stats"),
]
