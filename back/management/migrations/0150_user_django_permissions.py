from django.db import migrations


PERMISSION_DEFINITIONS = [
    ("view_api_schema", "Can view API schema"),
    ("view_database_schema", "Can view database schema"),
    ("matching_user", "Can perform matching operations"),
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
