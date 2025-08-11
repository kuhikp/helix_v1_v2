# Generated migration to alter id field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data_migration_utility', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='datamigrationutility',
            name='id',
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
    ]
