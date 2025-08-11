# Generated migration to remove site_meta_details_id field from database

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('data_migration_utility', '0002_remove_site_meta_details_field'),
    ]

    operations = [
        migrations.RunSQL(
            """
            ALTER TABLE data_migration_utility_datamigrationutility 
            DROP FOREIGN KEY data_migration_utili_site_meta_details_id_ddcc6e8b_fk_site_mana;
            """,
            reverse_sql=""
        ),
        migrations.RunSQL(
            "ALTER TABLE data_migration_utility_datamigrationutility DROP COLUMN site_meta_details_id;",
            reverse_sql="ALTER TABLE data_migration_utility_datamigrationutility ADD COLUMN site_meta_details_id INTEGER;"
        ),
    ]
