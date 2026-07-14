from django.db import migrations


class Migration(migrations.Migration):
    """Rename the adopted table to follow the open_chat app naming convention."""

    dependencies = [
        ("open_chat", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelTable(
            name="openchatconfiguration",
            table=None,
        ),
    ]
