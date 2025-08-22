from django import forms
from .models import SiteListDetails, SiteMetaDetails

class SiteListDetailsForm(forms.ModelForm):
    class Meta:
        model = SiteListDetails
        fields = ['website_url']
        widgets = {
            'website_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter website URL...'
            })
        }

class SiteMetaDetailsForm(forms.ModelForm):
    class Meta:
        model = SiteMetaDetails
        fields = '__all__'
        widgets = {
            'site_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter site page URL...',
                'required': True
            }),
            'helix_v1_component': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter Helix V1 components (comma-separated)...'
            }),
            'helix_v2_compatible_component': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter V2 compatible components (comma-separated)...'
            }),
            'helix_v2_non_compatible_component': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter V2 non-compatible components (comma-separated)...'
            }),
            'v2_compatible_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'style': 'display: none;'  # Hide as we'll show it in count display
            }),
            'v2_non_compatible_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'style': 'display: none;'  # Hide as we'll show it in count display
            }),
            'custom_component': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter custom components (comma-separated)...'
            }),
            'custom_component_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'style': 'display: none;'  # Hide as we'll show it in count display
            }),
        }
        labels = {
            'site_url': 'Site Page URL',
            'helix_v1_component': 'Helix V1 Components',
            'helix_v2_compatible_component': 'V2 Compatible Components',
            'helix_v2_non_compatible_component': 'V2 Non-Compatible Components',
            'v2_compatible_count': 'Compatible Components Count',
            'v2_non_compatible_count': 'Non-Compatible Components Count',
            'custom_component': 'Custom Components',
            'custom_component_count': 'Custom Components Count',
        }
        help_texts = {
            'site_url': 'Enter the full URL of the specific page being analyzed',
            'helix_v1_component': 'List all Helix V1 components found on this page, separated by commas',
            'helix_v2_compatible_component': 'List components that are compatible with Helix V2, separated by commas',
            'helix_v2_non_compatible_component': 'List components that are not compatible with Helix V2, separated by commas',
            'custom_component': 'List any custom components specific to this implementation, separated by commas',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Exclude site_list_details from the form as it should be set programmatically
        if 'site_list_details' in self.fields:
            del self.fields['site_list_details']
