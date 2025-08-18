from django.db import models
from django.conf import settings
from django.utils import timezone


class TagMapper(models.Model):
    """
    TagMapper model represents a reusable mapping block that defines how V1 components 
    should be transformed to V2 components.
    """
    CATEGORY_CHOICES = [
        ('layout', 'Layout Component'),
        ('form', 'Form Component'),
        ('media', 'Media Component'),
        ('interactive', 'Interactive Element'),
        ('ui', 'UI Component'),
        ('other', 'Other')
    ]
    
    v1_component_name = models.CharField(max_length=255)
    v2_component_name = models.CharField(max_length=255)
    weight = models.FloatField(default=0.0)
    description = models.TextField(blank=True, help_text="Optional description of this mapping")
    mapping_rules = models.JSONField(blank=True, null=True, help_text="JSON mapping rules for transformation")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    used_in_website = models.IntegerField(default=0, help_text="Number of websites using this mapping")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                   null=True, blank=True, related_name='created_mappers')
    
    def __str__(self):
        return f"{self.v1_component_name} -> {self.v2_component_name} (weight: {self.weight})"
    
    def get_usage_count(self):
        """Returns the number of migrations using this mapper"""
        from data_migration_utility.models import DataMigrationUtility
        # This assumes DataMigrationUtility has a many-to-many relationship with TagMapper
        # If not, this would need to be adjusted based on your actual relationship
        return DataMigrationUtility.objects.filter(tagmappers=self).count()

class ComplexityParameter(models.Model):
    """
    Single configuration model to define complexity parameters for website analysis.
    Only one record should exist in this table for global configuration.
    """
    COMPLEXITY_TYPE_CHOICES = [
        ('simple', 'Simple'),
        ('medium', 'Medium'),
        ('complex', 'Complex'),
    ]
    
    complexity_type = models.CharField(
        max_length=20,
        choices=COMPLEXITY_TYPE_CHOICES,
        default='medium',
        help_text="Overall complexity type classification for the site configuration"
    )
    number_of_pages = models.PositiveIntegerField(
        default=100,
        help_text="Base number of pages to consider for complexity calculation"
    )
    number_of_helix_v2_compatible = models.PositiveIntegerField(
        default=50,
        help_text="Number of Helix V2 compatible components"
    )
    number_of_helix_v2_non_compatible = models.PositiveIntegerField(
        default=20,
        help_text="Number of Helix V2 non-compatible components"
    )
    number_of_custom_components = models.PositiveIntegerField(
        default=10,
        help_text="Number of custom components"
    )
    total_simple_components = models.PositiveIntegerField(
        default=30,
        help_text="Total number of simple complexity components"
    )
    total_medium_components = models.PositiveIntegerField(
        default=40,
        help_text="Total number of medium complexity components"
    )
    total_complex_components = models.PositiveIntegerField(
        default=30,
        help_text="Total number of complex complexity components"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="User who last updated the configuration"
    )


    class Meta:
        verbose_name = "Complexity Parameter Configuration"
        verbose_name_plural = "Complexity Parameter Configuration"
        unique_together = ('complexity_type',)

    # Removed singleton logic: now allows one config per complexity_type

    def __str__(self):
        return f"Complexity Configuration (Pages: {self.number_of_pages}, V2 Compatible: {self.number_of_helix_v2_compatible})"



# Create your models here.

class Tag(models.Model):
    COMPLEXITY_CHOICES = [
        ('simple', 'Simple'),
        ('medium', 'Medium'),
        ('complex', 'Complex'),
    ]

    VERSION_CHOICES = [
        ('V1', 'Version 1'),
        ('V2', 'Version 2'),
    ]

    IS_MANAGED_BY_CHOICES = [
        ('manual', 'Manual'),
        ('automated', 'Automated'),
    ]

    name = models.CharField(max_length=100)
    path = models.CharField(max_length=255)
    details = models.TextField()
    version = models.CharField(max_length=2, choices=VERSION_CHOICES)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_tags')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='updated_tags')
    complexity = models.CharField(max_length=10, choices=COMPLEXITY_CHOICES)
    is_managed_by = models.CharField(max_length=10, choices=IS_MANAGED_BY_CHOICES)
    tags_extractor = models.ForeignKey('TagsExtractor', on_delete=models.SET_NULL, null=True, blank=True, related_name='tags')
    theme_type = models.CharField(max_length=255, blank=True, null=True)
    used_in_website = models.IntegerField(default=0, help_text="Number of websites using this component")

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ('name', 'theme_type', 'version')

class TagsExtractor(models.Model):
    VERSION_CHOICES = [
        ('V1', 'Version 1'),
        ('V2', 'Version 2'),
    ]
    
    EXTRACTION_METHOD_CHOICES = [
        ('GITAPI', 'GitHub API Repository'),
        ('CLONE', 'Local Repository Clone'),
    ]
    
    version_value = models.CharField(max_length=2, choices=VERSION_CHOICES)
    repo_url = models.URLField(unique=True)
    extraction_method = models.CharField(max_length=10, choices=EXTRACTION_METHOD_CHOICES, default='GITAPI')
    def has_pending_pages(self):
        return self.start_page < self.total_pages
    created_at = models.DateTimeField(auto_now_add=True)
    imported = models.BooleanField(default=False)
    total_pages = models.IntegerField(default=0)
    start_page = models.IntegerField(default=1)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.repo_url} ({self.version_value})"
