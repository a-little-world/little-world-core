from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0161_alter_state_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="openchatconfiguration",
            name="open_chat_host",
            field=models.CharField(
                default="http://host.docker.internal:1984",
                max_length=255,
            ),
            preserve_default=False,
        ),
    ]
