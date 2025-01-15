import uuid
from django.db import migrations, models

def generate_uuid5(apps, schema_editor):
    PatenmatchUser = apps.get_model('patenmatch', 'PatenmatchUser')
    namespace = uuid.UUID("8b0a546c-92d3-11ec-b909-0242ac120002")  # Use a fixed namespace UUID

    for user in PatenmatchUser.objects.all():
        # Generate UUID5 using user ID as the name within a fixed namespace
        user.uuid = uuid.uuid5(namespace, str(user.id))
        user.save(update_fields=['uuid'])

class Migration(migrations.Migration):

    dependencies = [
        ('patenmatch', '0010_patenmatchuser_spoken_languages'),
    ]

    operations = [
        migrations.AddField(
            model_name='patenmatchuser',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.RunPython(generate_uuid5),
        migrations.AlterField(
            model_name='patenmatchuser',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]