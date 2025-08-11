from django import forms
from .models import DataMigrationUtility

class DataMigrationUtilityForm(forms.ModelForm):
    class Meta:
        model = DataMigrationUtility
        fields = ['v1_body', 'v1_css', 'v1_js', 'v2_body', 'v2_css', 'v2_js']
