# Generated migration for adding complexity_type field
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('tag_manager_component', '0013_create_complexityparameter'),
    ]

    operations = [
        migrations.AddField(
            model_name='complexityparameter',
            name='complexity_type',
            field=models.CharField(
                choices=[
                    ('simple', 'Simple'),
                    ('medium', 'Medium'),
                    ('complex', 'Complex'),
                ],
                default='medium',
                help_text='Overall complexity type classification for the site configuration',
                max_length=20
            ),
        ),
    ]
