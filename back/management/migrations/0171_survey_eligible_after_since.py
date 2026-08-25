"""Lower bound on when an eligible-after condition counts."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0170_drop_post_call_review"),
    ]

    operations = [
        migrations.AddField(
            model_name="surveycampaign",
            name="eligible_after_since",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Lower bound on when eligible_after_event counts. Only people who reached that "
                    "condition on or after this instant are eligible. Empty means any time. Ignored "
                    "when the event is empty."
                ),
                null=True,
            ),
        ),
    ]
