# Rename is_random_call_chat → is_temporary (same meaning, clearer name).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0011_chat_seven_days_inactive_email_send_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="chat",
            old_name="is_random_call_chat",
            new_name="is_temporary",
        ),
    ]
