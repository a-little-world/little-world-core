from django.db import migrations, models


def deactivate_duplicate_active_sessions(apps, schema_editor):
    LivekitSession = apps.get_model("video", "LivekitSession")
    extra_ids = []
    seen_rooms = set()
    for session_id, room_id in (
        LivekitSession.objects.filter(is_active=True, room_id__isnull=False)
        .order_by("room_id", "created_at", "pk")
        .values_list("id", "room_id")
        .iterator()
    ):
        if room_id in seen_rooms:
            extra_ids.append(session_id)
        else:
            seen_rooms.add(room_id)
    if extra_ids:
        LivekitSession.objects.filter(id__in=extra_ids).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("video", "0029_randomcalllobbyuser_first_joined_at"),
    ]

    operations = [
        migrations.RunPython(deactivate_duplicate_active_sessions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="livekitsession",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True), ("room__isnull", False)),
                fields=("room",),
                name="unique_active_livekit_session_per_room",
            ),
        ),
    ]
