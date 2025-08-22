from django.db import models
from django.utils import timezone

class SiteListDetails(models.Model):
    COMPLEXITY_CHOICES = [
        ('simple', 'Simple'),
        ('medium', 'Medium'),
        ('complex', 'Complex'),
    ]

    complexity = models.CharField(
        max_length=10,
        choices=COMPLEXITY_CHOICES,
        default='medium',
        help_text='Site complexity classification (simple, medium, complex)'
    )
    complexity_configuration = models.TextField(
        blank=True, 
        null=True,
        help_text='JSON configuration data used to determine the complexity of this site'
    )
    website_url = models.URLField(unique=True)
    total_pages = models.IntegerField(default=0)
    helix_site_id = models.IntegerField(default=0)

    helix_v1_component = models.TextField(blank=True, null=True)
    helix_v2_compatible_component = models.TextField(blank=True, null=True)
    helix_v2_non_compatible_component = models.TextField(blank=True, null=True)
    v2_compatible_count = models.IntegerField(default=0)
    v2_non_compatible_count = models.IntegerField(default=0)
    custom_component = models.TextField(blank=True, null=True)
    is_imported = models.BooleanField(default=False)
    last_analyzed = models.DateTimeField(blank=True, null=True, help_text='Date and time when the site was last analyzed')

    def __str__(self):
        return self.website_url

class SiteMetaDetails(models.Model):
    site_list_details = models.ForeignKey(SiteListDetails, on_delete=models.CASCADE, related_name='meta_details')
    site_url = models.URLField()
    helix_v1_component = models.TextField(blank=True, null=True)
    helix_v2_compatible_component = models.TextField(blank=True, null=True)
    helix_v2_non_compatible_component = models.TextField(blank=True, null=True)
    v2_compatible_count = models.IntegerField(default=0)
    v2_non_compatible_count = models.IntegerField(default=0)
    custom_component = models.TextField(blank=True, null=True)
    custom_component_count = models.IntegerField(default=0)

    def __str__(self):
        return self.site_url
