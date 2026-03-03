# Merged: 0133 (match_type), 0134 (rename confirming_user), 0135 (alter confirming_user related_name).
# Also adds MatchType.TEMPORARY and removes Match.is_random_call_match.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("management", "0132_state_force_match_eligible_state_has_match_priority_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="match_type",
            field=models.CharField(
                choices=[
                    ("standard", "Standard Match"),
                    ("random_call", "Random Call Match"),
                    ("temporary", "Temporary Match"),
                ],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.RemoveField(
            model_name="match",
            name="is_random_call_match",
        ),
        migrations.AddField(
            model_name="proposedmatch",
            name="match_type",
            field=models.CharField(
                choices=[
                    ("standard", "Standard Match"),
                    ("random_call", "Random Call Match"),
                    ("temporary", "Temporary Match"),
                ],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.RenameField(
            model_name="proposedmatch",
            old_name="learner_when_created",
            new_name="confirming_user",
        ),
        migrations.AlterField(
            model_name="proposedmatch",
            name="confirming_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="unconfirmed_match_confirming_user",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
