from django.db import models
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings


class KnowledgeBase(models.Model):
    """
    Knowledge Base model to store V1 and V2 component examples for reference.
    Only admins can create/edit these entries.
    """
    title = models.CharField(max_length=200, help_text="Descriptive title for this knowledge base entry")
    component_name = models.CharField(max_length=100, help_text="Name of the component (e.g., helix-image, helix-accordion)")
    v1_code = models.TextField(help_text="V1 version of the component code")
    v2_code = models.TextField(help_text="V2 version of the component code")
    description = models.TextField(blank=True, help_text="Optional description or notes about this migration pattern")
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags for categorization")
    is_active = models.BooleanField(default=True, help_text="Whether this entry is active and visible")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='knowledge_entries')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Knowledge Base Entry"
        verbose_name_plural = "Knowledge Base Entries"

    def __str__(self):
        return f"{self.title} - {self.component_name}"

    def get_absolute_url(self):
        return reverse('knowledge_base_detail', kwargs={'pk': self.pk})

    def get_tags_list(self):
        """Return tags as a list."""
        return [tag.strip() for tag in self.tags.split(',') if tag.strip()]

    def get_v1_preview(self, max_length=100):
        """Get a preview of V1 code."""
        return self.v1_code[:max_length] + '...' if len(self.v1_code) > max_length else self.v1_code

    def get_v2_preview(self, max_length=100):
        """Get a preview of V2 code."""
        return self.v2_code[:max_length] + '...' if len(self.v2_code) > max_length else self.v2_code

class DataMigrationUtility(models.Model):
    v1_body = models.TextField(blank=True, null=True)
    v1_css = models.TextField(blank=True, null=True)
    v1_js = models.TextField(blank=True, null=True)
    v2_body = models.TextField(blank=True, null=True)
    v2_css = models.TextField(blank=True, null=True)
    v2_js = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Data Migration"
        verbose_name_plural = "Data Migrations"

    def __str__(self):
        return f"Migration #{self.pk} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    def get_absolute_url(self):
        return reverse('data_migration_detail', kwargs={'pk': self.pk})

    def has_v1_content(self):
        return any([self.v1_body, self.v1_css, self.v1_js])

    def has_v2_content(self):
        return any([self.v2_body, self.v2_css, self.v2_js])

    def is_migration_complete(self):
        return self.has_v1_content() and self.has_v2_content()

    def get_v1_content_summary(self):
        content_types = []
        if self.v1_body:
            content_types.append(f"Body ({len(self.v1_body)} chars)")
        if self.v1_css:
            content_types.append(f"CSS ({len(self.v1_css)} chars)")
        if self.v1_js:
            content_types.append(f"JS ({len(self.v1_js)} chars)")
        return ", ".join(content_types) if content_types else "No content"

    def get_v2_content_summary(self):
        content_types = []
        if self.v2_body:
            content_types.append(f"Body ({len(self.v2_body)} chars)")
        if self.v2_css:
            content_types.append(f"CSS ({len(self.v2_css)} chars)")
        if self.v2_js:
            content_types.append(f"JS ({len(self.v2_js)} chars)")
        return ", ".join(content_types) if content_types else "No content"

    def get_status(self):
        if not self.has_v1_content():
            return 'empty'
        if not self.has_v2_content():
            return 'pending'
        if self.updated_at and self.created_at != self.updated_at:
            return 'modified'
        return 'completed'

    def get_status_display(self):
        status = self.get_status()
        return {
            'empty': 'Empty',
            'pending': 'Pending',
            'modified': 'Modified',
            'completed': 'Completed'
        }.get(status, 'Unknown')
