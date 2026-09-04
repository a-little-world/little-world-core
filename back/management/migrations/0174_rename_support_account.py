from django.conf import settings
from django.db import migrations


def rename_support_account(apps, schema_editor):
    User = apps.get_model("management", "User")
    Profile = apps.get_model("management", "Profile")

    user = User.objects.filter(email="tim.timschupp+420@gmail.com").first()
    if user is None:
        return

    User.objects.filter(pk=user.pk).update(
        first_name=settings.MATCHING_USER_FIRST_NAME,
        last_name=settings.MATCHING_USER_SECOND_NAME,
    )
    Profile.objects.filter(user_id=user.pk).update(
        first_name=settings.MATCHING_USER_FIRST_NAME,
        second_name=settings.MATCHING_USER_SECOND_NAME,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0173_supporttasknote"),
    ]

    operations = [
        migrations.RunPython(rename_support_account, migrations.RunPython.noop),
    ]
