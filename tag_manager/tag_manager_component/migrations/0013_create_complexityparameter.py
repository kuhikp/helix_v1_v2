# Generated for ComplexityParameter model

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tag_manager_component', '0012_remove_complexityparameter_single_complexity_config'),
    ]

    operations = [
        migrations.RunSQL(
            """
            CREATE TABLE IF NOT EXISTS `tag_manager_component_complexityparameter` (
                `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
                `number_of_pages` int unsigned NOT NULL DEFAULT 100,
                `number_of_helix_v2_compatible` int unsigned NOT NULL DEFAULT 50,
                `number_of_helix_v2_non_compatible` int unsigned NOT NULL DEFAULT 20,
                `number_of_custom_components` int unsigned NOT NULL DEFAULT 10,
                `total_simple_components` int unsigned NOT NULL DEFAULT 30,
                `total_medium_components` int unsigned NOT NULL DEFAULT 40,
                `total_complex_components` int unsigned NOT NULL DEFAULT 30,
                `created_at` datetime(6) NOT NULL,
                `updated_at` datetime(6) NOT NULL,
                `updated_by_id` bigint NULL
            );
            """,
            reverse_sql="DROP TABLE IF EXISTS `tag_manager_component_complexityparameter`;"
        ),
    ]