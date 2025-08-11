from django.core.management.base import BaseCommand
from tag_manager_component.models import Tag
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Create sample tags for Tag Manager'

    def handle(self, *args, **kwargs):
        User = get_user_model()
        admin_user = User.objects.filter(role='admin').first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No admin user found. Please create an admin user first.'))
            return
        if Tag.objects.count() == 0:
            Tag.objects.create(
                name='Sample Tag 1',
                path='/sample/tag1',
                details='This is the first sample tag.',
                version='V1',
                created_by=admin_user,
                updated_by=admin_user,
                complexity='simple',
                is_managed_by='manual',
            )
            Tag.objects.create(
                name='Sample Tag 2',
                path='/sample/tag2',
                details='This is the second sample tag.',
                version='V2',
                created_by=admin_user,
                updated_by=admin_user,
                complexity='complex',
                is_managed_by='automated',
            )
            self.stdout.write(self.style.SUCCESS('Sample tags created.'))
        else:
            self.stdout.write(self.style.WARNING('Sample tags already exist.'))