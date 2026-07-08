from django.db import migrations


class Migration(migrations.Migration):
    """Remove OpenChatConfiguration from the management app state only.

    The model moves to the dedicated ``open_chat`` app. The underlying database
    table is left untouched here and adopted (then renamed) by the open_chat
    migrations, so no data is lost.
    """

    dependencies = [
        ("management", "0163_remove_open_chat_interaction_overwrite"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="OpenChatConfiguration"),
            ],
            database_operations=[],
        ),
    ]
