# Generated migration to remove site_meta_details_id field from database

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('data_migration_utility', '0002_remove_site_meta_details_field'),
    ]

    def drop_fk_and_column(apps, schema_editor):
        # Remove FK and column from data_migration_utility_datamigrationutility
        table = "data_migration_utility_datamigrationutility"
        fk_name = "data_migration_utili_site_meta_details_id_ddcc6e8b_fk_site_mana"
        with schema_editor.connection.cursor() as cursor:
            # Check if foreign key exists
            cursor.execute(f"SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_NAME='{table}' AND CONSTRAINT_NAME='{fk_name}';")
            result = cursor.fetchone()
            if result:
                cursor.execute(f"ALTER TABLE {table} DROP FOREIGN KEY {fk_name};")
            # Check if column exists
            cursor.execute(f"SHOW COLUMNS FROM {table} LIKE 'site_meta_details_id';")
            col_result = cursor.fetchone()
            if col_result:
                cursor.execute(f"ALTER TABLE {table} DROP COLUMN site_meta_details_id;")

        # Remove check constraint from tag_manager_component_complexityparameter
        comp_table = "tag_manager_component_complexityparameter"
        constraint_name = 'single_complexity_config'
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(f"SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_NAME='{comp_table}' AND CONSTRAINT_NAME='{constraint_name}' AND CONSTRAINT_TYPE='CHECK';")
            check_result = cursor.fetchone()
            if check_result:
                cursor.execute(f"ALTER TABLE {comp_table} DROP CHECK {constraint_name};")

    operations = [
        migrations.RunPython(drop_fk_and_column),
    ]
