from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0153_alter_state_options_shortlink_archived_at_and_more"),
        ("management", "0154_user_uuid_backfill_and_sync_hash"),
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
                    ("apply_management_permissions", "Can apply management permissions"),
                ]
            },
        ),
    ]
