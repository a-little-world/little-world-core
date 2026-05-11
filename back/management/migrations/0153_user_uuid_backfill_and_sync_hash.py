import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0152_remove_state_extra_user_permissions_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="user",
            name="old_backend_user_hash",
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True),
        ),
    ]
