"""
Idempotent dev seed for the volunteer self-onboarding walkthrough course.
Used when EMPHIRIAL=1 (see back/entry.sh).
"""

from management.models.courses import (
    ChapterQuizStep,
    Course,
    CourseChapter,
    UserTypeAvailabilityChoices,
)

_CHAPTERS = [
    {
        "chapter_id": "self_onboarding_c1",
        "order": 0,
        "available_to": UserTypeAvailabilityChoices.VOLUNTEER,
        "title": "Kapitel 1",
        "description": "",
        "video_url": "https://youtu.be/2djMjpVy3ss",
        "video_title": "Little World Einführung - Teil 1",
        "completed_title": "",
        "completed_description": "",
        "completed_additional_text": "",
        "completed_cta_label": "",
        "quiz_steps": [
            {
                "order": 1,
                "question": "Welche gehören zu unseren Werten?",
                "answers": [
                    "Respekt, Zuverlässigkeit, Offenheit",
                    "Sprachliche Perfektion",
                    "Nichts davon",
                ],
                "correct_answer": "Respekt, Zuverlässigkeit, Offenheit",
            },
        ],
    },
    {
        "chapter_id": "self_onboarding_c2",
        "order": 1,
        "available_to": UserTypeAvailabilityChoices.VOLUNTEER,
        "title": "Kapitel 2",
        "description": "",
        "video_url": "https://youtu.be/MtjitzgSnm8",
        "video_title": "Little World Einführung - Teil 2",
        "completed_title": "",
        "completed_description": "",
        "completed_additional_text": "",
        "completed_cta_label": "",
        "quiz_steps": [
            {
                "order": 1,
                "question": "Wie kommunizieren wir miteinander?",
                "answers": [
                    "Über persönliche Telefonnummern oder private Messenger-Dienste wie WhatsApp.",
                    "Direkt über die Little-World-Plattform – inklusive Chat, Video und zusätzlicher Tools.",
                    "Vor Ort in deiner Stadt.",
                ],
                "correct_answer": (
                    "Direkt über die Little-World-Plattform – inklusive Chat, Video und zusätzlicher Tools."
                ),
            },
        ],
    },
    {
        "chapter_id": "self_onboarding_c3",
        "order": 2,
        "available_to": UserTypeAvailabilityChoices.VOLUNTEER,
        "title": "Kapitel 3",
        "description": "",
        "video_url": "https://youtu.be/nv2V01yCHjw",
        "video_title": "Little World Einführung - Teil 3",
        "completed_title": "Kurs abgeschlossen",
        "completed_description": (
            "Großartig! Du hast deinen Einführungs-Rundgang abgeschlossen und kannst jetzt bei Little World starten."
        ),
        "completed_additional_text": (
            "Wir suchen ein:e passende:n Gesprächspartner:in für dich. Bis dahin laden wir dich ein, "
            "in diesen ersten Tagen unsere Community kennenzulernen – komm einfach zu einem unserer Gruppengespräche!"
        ),
        "completed_cta_label": "",
        "quiz_steps": [
            {
                "order": 1,
                "question": "Wie lange soll ich pro Woche mit meinem Gesprächspartner sprechen?",
                "answers": [
                    "Jeden Tag",
                    "30 Minuten pro Woche für 10 Wochen",
                    "Einmal reicht",
                ],
                "correct_answer": "30 Minuten pro Woche für 10 Wochen",
            },
        ],
    },
]


def _sync_chapters(course: Course, chapters_data: list[dict]) -> None:
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


def create_self_onboarding_course() -> Course:
    """
    Creates or updates the self-onboarding course and its chapters/quiz steps.
    Safe to run on every local startup (EMPHIRIAL=1).
    """
    course, created = Course.objects.update_or_create(
        slug=Course.SELF_ONBOARDING_SLUG,
        defaults={
            "title": "Einführungs-Rundgang",
            "description": "",
            "is_active": True,
            "is_listed": False,
            "available_to": UserTypeAvailabilityChoices.VOLUNTEER,
        },
    )
    chapters_data = [dict(ch) for ch in _CHAPTERS]
    _sync_chapters(course, chapters_data)
    action = "created" if created else "updated"
    print(f"Self-onboarding course ({Course.SELF_ONBOARDING_SLUG}): {action}.")
    return course
