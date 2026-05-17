import uuid

from django.db import migrations, models


def backfill_user_uuid(apps, schema_editor):
    User = apps.get_model("management", "User")
    for user in User.objects.filter(uuid__isnull=True).only("id").iterator(chunk_size=1000):
        User.objects.filter(pk=user.pk).update(uuid=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0153_alter_state_options_shortlink_archived_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="uuid",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(backfill_user_uuid, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name="user",
            name="old_backend_user_hash",
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True),
        ),
    ]
