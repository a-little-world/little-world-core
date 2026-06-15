from django.db import migrations, models

import management.models.open_chat_configuration


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0162_open_chat_configuration_host"),
    ]

    operations = [
        migrations.AlterField(
            model_name="openchatconfiguration",
            name="open_chat_host",
            field=models.CharField(
                default=management.models.open_chat_configuration.DEFAULT_OPEN_CHAT_HOST,
                max_length=255,
            ),
        ),
    ]
