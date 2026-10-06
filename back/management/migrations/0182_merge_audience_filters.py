from django.db import migrations, models


AUDIENCE_FILTER_CHOICES = [
    ("learners_with_a1a2", "Learners with A1/A2 German"),
    ("learners_above_a1a2", "Learners above A1/A2"),
    ("volunteers", "All registered volunteers"),
    ("learners", "All registered learners"),
    ("onboarded_volunteers", "Onboarded volunteers"),
    ("onboarded_learners", "Onboarded learners"),
    ("learners_outside_germany", "Learners outside Germany"),
    ("random_call_users", "Random-call users"),
    ("match_eligible_users", "Match-eligible users"),
    ("nrw_residents", "NRW residents"),
    ("none", "None"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0181_state_search_activation_token"),
    ]

    operations = [
        migrations.AlterField(
            model_name="banner",
            name="custom_filter",
            field=models.CharField(choices=AUDIENCE_FILTER_CHOICES, default="none", max_length=255),
        ),
        migrations.AlterField(
            model_name="communityevent",
            name="custom_filter",
            field=models.CharField(choices=AUDIENCE_FILTER_CHOICES, default="none", max_length=255),
        ),
        migrations.AlterField(
            model_name="surveycampaign",
            name="audience_value",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Company name when audience_type is 'company', or an AudienceFilters value when "
                    "it is 'filter'. Empty for everyone."
                ),
                max_length=255,
            ),
        ),
    ]
