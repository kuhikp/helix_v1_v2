from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from django.db import transaction
from django.utils import timezone
import json

from tag_manager_component.models import (
    TagMapper, ComplexityParameter, Tag, TagsExtractor
)
from site_manager.models import SiteListDetails, SiteMetaDetails
from data_migration_utility.models import DataMigrationUtility

User = get_user_model()


class Command(BaseCommand):
    help = 'Import sample data from tag_manager_db for developer setup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Flush existing data before importing',
        )

    def handle(self, *args, **options):
        if options['flush']:
            self.stdout.write(self.style.WARNING('Flushing existing data...'))
            self.flush_data()

        self.stdout.write(self.style.SUCCESS('Starting sample data import...'))

        try:
            with transaction.atomic():
                self.create_sample_users()
                self.create_sample_complexity_parameters()
                self.create_sample_tag_extractors()

            self.stdout.write(self.style.SUCCESS('Sample data import completed successfully!'))
            self.display_summary()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during import: {str(e)}'))

    def flush_data(self):
        """Flush existing data from the database."""
        models_to_flush = [
            SiteMetaDetails, SiteListDetails, DataMigrationUtility,
            Tag, TagMapper, TagsExtractor, ComplexityParameter
        ]
        for model in models_to_flush:
            model.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('All data flushed successfully.'))

    def create_sample_users(self):
        """Create sample users."""
        self.stdout.write('Creating sample users...')

        self.admin_user = self._create_user(
            username='admin@tagmanager.com',
            email='admin@tagmanager.com',
            first_name='Admin',
            last_name='User',
            role='admin',
            is_staff=True,
            is_superuser=True
        )

        self.tag_manager = self._create_user(
            username='tagmanager@tagmanager.com',
            email='tagmanager@tagmanager.com',
            first_name='Tag',
            last_name='Manager',
            role='tag_manager',
            is_staff=True
        )

    def _create_user(self, **kwargs):
        """Helper function to create a user."""
        user, created = User.objects.get_or_create(
            username=kwargs['username'],
            defaults=kwargs
        )
        if created:
            password = get_random_string(length=12)
            user.set_password(password)
            user.save()
            self.stdout.write(f"✓ Created user {kwargs['username']} with password: {password}")
        return user

    def create_sample_complexity_parameters(self):
        """Create sample complexity parameters."""
        self.stdout.write('Creating sample complexity parameters...')

        complexity_configs = [
            {
                'complexity_type': 'simple',
                'number_of_pages': 50,
                'number_of_helix_v2_compatible': 80,
                'number_of_helix_v2_non_compatible': 15,
                'number_of_custom_components': 5,
                'total_simple_components': 60,
                'total_medium_components': 30,
                'total_complex_components': 10,
            },
            {
                'complexity_type': 'medium',
                'number_of_pages': 150,
                'number_of_helix_v2_compatible': 120,
                'number_of_helix_v2_non_compatible': 40,
                'number_of_custom_components': 20,
                'total_simple_components': 80,
                'total_medium_components': 70,
                'total_complex_components': 30,
            },
            {
                'complexity_type': 'complex',
                'number_of_pages': 500,
                'number_of_helix_v2_compatible': 200,
                'number_of_helix_v2_non_compatible': 100,
                'number_of_custom_components': 50,
                'total_simple_components': 150,
                'total_medium_components': 150,
                'total_complex_components': 50,
            }
        ]

        for config in complexity_configs:
            complexity_param, created = ComplexityParameter.objects.get_or_create(
                complexity_type=config['complexity_type'],
                defaults={**config, 'updated_by': self.admin_user}
            )
            if created:
                self.stdout.write(f"✓ Created {config['complexity_type']} complexity configuration")

    def create_sample_tag_extractors(self):
        """Create sample tag extractors."""
        self.stdout.write('Creating sample tag extractors...')

        extractors_data = [
            {
                'version_value': 'V1',
                'repo_url': 'https://github.com/pfizer/helix-extras.git',
                'extraction_method': 'CLONE',
                'description': 'Helix V1 components repository',
                'imported': False,
            },
            {
                'version_value': 'V1',
                'repo_url': 'https://github.com/pfizer/helix-nextgen-webcomponent-theme.git',
                'extraction_method': 'CLONE',
                'description': 'Helix V1 components repository',
                'imported': False,
            },
            {
                'version_value': 'V1',
                'repo_url': 'https://github.com/pfizer/helix-web-components.git',
                'extraction_method': 'CLONE',
                'description': 'Helix V1 components repository',
                'imported': False,
            },
            {
                'version_value': 'V2',
                'repo_url': 'https://github.com/pfizer/hcp-galaxy-theme',
                'extraction_method': 'GITAPI',
                'description': 'Helix V2 components repository',
                'imported': False,
            },
            {
                'version_value': 'V2',
                'repo_url': 'https://github.com/pfizer/cdp-lite-theme',
                'extraction_method': 'CLONE',
                'description': 'Helix V2 components repository',
                'imported': False,
            }
        ]

        for extractor_data in extractors_data:
            extractor, created = TagsExtractor.objects.get_or_create(
                repo_url=extractor_data['repo_url'],
                defaults=extractor_data
            )
            if created:
                self.stdout.write(f"✓ Created extractor for {extractor_data['repo_url']}")

    def display_summary(self):
        """Display summary of imported data."""
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS('IMPORT SUMMARY'))
        self.stdout.write('=' * 50)

        summary_data = {
            'Users': User.objects.count(),
            'Complexity Parameters': ComplexityParameter.objects.count(),
            'Tag Extractors': TagsExtractor.objects.count(),
            'Tags': Tag.objects.count(),
            'Tag Mappers': TagMapper.objects.count(),
            'Sites': SiteListDetails.objects.count(),
            'Site Meta Details': SiteMetaDetails.objects.count(),
            'Data Migrations': DataMigrationUtility.objects.count(),
        }

        for key, value in summary_data.items():
            self.stdout.write(f"{key}: {value}")

        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS('LOGIN CREDENTIALS'))
        self.stdout.write('=' * 50)
        self.stdout.write('Admin User:')
        self.stdout.write('  Username: admin@tagmanager.com')
        self.stdout.write('  Password: Password Copy From Terminal')
        self.stdout.write('  Email: admin@tagmanager.com')
        self.stdout.write('')
        self.stdout.write('Tag Manager User:')
        self.stdout.write('  Username: tagmanager@tagmanager.com')
        self.stdout.write('  Password: Password Copy From Terminal')
        self.stdout.write('  Email: tagmanager@tagmanager.com')
        self.stdout.write('=' * 50)
