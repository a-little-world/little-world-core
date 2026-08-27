from django.conf import settings
from django.db import migrations, models


def copy_existing_assignees(apps, schema_editor):
    SupportTask = apps.get_model("management", "SupportTask")
    through_model = SupportTask.assignees.through
    through_model.objects.bulk_create(
        [
            through_model(supporttask_id=task_id, user_id=assigned_to_id)
            for task_id, assigned_to_id in SupportTask.objects.exclude(assigned_to_id=None).values_list(
                "id", "assigned_to_id"
            )
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0170_mobile_device_session_active_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="supporttask",
            name="assignees",
            field=models.ManyToManyField(
                blank=True,
                related_name="assigned_support_tasks",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(copy_existing_assignees, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="supporttask",
            name="assigned_to",
        ),
    ]
