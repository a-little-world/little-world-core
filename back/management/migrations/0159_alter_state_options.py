from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0158_course_coursechapter_chapterquizstep_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="state",
            options={
                "permissions": [
                    ("view_api_schema", "Can view API schema"),
                    ("view_database_schema", "Can view database schema"),
                    ("matching_user", "Can perform matching operations"),
                    ("use_random_calls", "Can use random calls feature"),
                    ("open_chat_access", "Can access open chat"),
                    ("edit_open_chat_configuration", "Can edit open chat configuration"),
                    ("apply_management_permissions", "Can apply management permissions"),
                ]
            },
        ),
    ]
