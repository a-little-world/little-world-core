from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0179_support_task_scheduled_at_note_author"),
    ]

    operations = [
        migrations.AddField(
            model_name="prematchingappointment",
            name="calcom_booking_uid",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]