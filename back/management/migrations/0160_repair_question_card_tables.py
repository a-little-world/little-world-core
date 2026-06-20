# pylint: disable=protected-access

from django.db import migrations


def create_missing_question_card_tables(apps, schema_editor):
    """
    Repair environments where 0159 was recorded as applied before the new
    question-card tables existed.
    """
    with schema_editor.connection.cursor() as cursor:
        existing_tables = set(schema_editor.connection.introspection.table_names(cursor))

    for model_name in (
        "QuestionCardCategory",
        "QuestionCard",
        "UserQuestionCardPreference",
    ):
        model = apps.get_model("management", model_name)
        if model._meta.db_table not in existing_tables:
            schema_editor.create_model(model)
            existing_tables.add(model._meta.db_table)


class Migration(migrations.Migration):
    dependencies = [
        ("management", "0159_refactor_question_cards"),
    ]

    operations = [
        migrations.RunPython(create_missing_question_card_tables, migrations.RunPython.noop),
    ]
