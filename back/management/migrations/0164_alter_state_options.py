from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0163_alter_openchatconfiguration_open_chat_host"),
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
                    ("manage_open_chat_access", "Manage Open Chat Access"),
                    ("apply_management_permissions", "Can apply management permissions"),
                ]
            },
        ),
    ]
