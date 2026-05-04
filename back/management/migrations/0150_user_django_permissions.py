from django.db import migrations


PERMISSION_DEFINITIONS = [
    ("view_api_schema", "Can view API schema"),
    ("view_database_schema", "Can view database schema"),
    ("view_docs", "Can view docs"),
    ("view_email_templates", "Can view email templates"),
    ("view_stats", "Can view stats"),
    ("matching_user", "Can perform matching operations"),
    ("uncensored_admin_matcher", "Can perform uncensored matching"),
    ("use_random_calls", "Can use random calls feature"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("management", "0149_alter_state_extra_user_permissions"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="state",
            options={
                "permissions": PERMISSION_DEFINITIONS,
            },
        ),
    ]
