import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Adopt the existing management_openchatconfiguration table into the open_chat app.

    Only the migration state changes here (the model now lives in this app); the
    physical table is reused as-is and renamed in the following migration.
    """

    initial = True

    dependencies = [
        ("management", "0164_remove_openchatconfiguration"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="OpenChatConfiguration",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                            ),
                        ),
                        ("open_chat_api_key", models.CharField(max_length=512)),
                        ("open_chat_user", models.CharField(max_length=255)),
                        (
                            "open_chat_host",
                            models.CharField(default="http://host.docker.internal:1984", max_length=255),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "user",
                            models.OneToOneField(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="open_chat_configuration",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "db_table": "management_openchatconfiguration",
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
