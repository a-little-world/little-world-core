from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('management', '0162_open_chat_interaction_overwrite'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='openchatconfiguration',
            name='interaction_overwrite',
        ),
    ]
