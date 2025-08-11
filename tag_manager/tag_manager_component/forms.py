from django import forms
from .models import Tag, TagsExtractor, TagMapper, ComplexityParameter
from django.forms import widgets

class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['name', 'path', 'details', 'version', 'complexity', 'is_managed_by']

class TagsExtractorForm(forms.ModelForm):
    class Meta:
        model = TagsExtractor
        fields = ['version_value', 'repo_url', 'total_pages', 'start_page', 'description']
        widgets = {
            'repo_url': forms.URLInput(attrs={
                'placeholder': 'https://github.com/user/repository',
                'class': 'form-control'
            }),
            'total_pages': forms.NumberInput(attrs={
                'min': 0,
                'value': 0,
                'placeholder': '0 for auto-detection',
                'class': 'form-control'
            }),
            'start_page': forms.NumberInput(attrs={
                'min': 1,
                'value': 1,
                'placeholder': '1',
                'class': 'form-control'
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Optional description for this extractor...',
                'class': 'form-control'
            }),
            'version_value': forms.Select(attrs={
                'class': 'form-select'
            })
        }

class TagMapperForm(forms.ModelForm):
    class Meta:
        model = TagMapper
        fields = ['v1_component_name', 'v2_component_name', 'weight']
        widgets = {
            'v2_component_name': widgets.TextInput(attrs={'placeholder': 'Comma separated V2 names'}),
            'weight': widgets.NumberInput(attrs={'min': 1, 'value': 1}),
        }

class ComplexityMappingForm(forms.Form):
    csv_file = forms.FileField(
        label='Upload CSV File',
        help_text='CSV file should contain columns: tag_name, complexity (simple/medium/complex)',
        widget=forms.FileInput(attrs={
            'accept': '.csv',
            'class': 'form-control'
        })
    )
    
    def clean_csv_file(self):
        file = self.cleaned_data['csv_file']
        if not file.name.endswith('.csv'):
            raise forms.ValidationError('Please upload a CSV file.')
        
        if file.size > 5 * 1024 * 1024:  # 5MB limit
            raise forms.ValidationError('File size cannot exceed 5MB.')
        
        return file

class ComplexityParameterForm(forms.ModelForm):
    """Form for managing complexity parameter configuration"""
    
    class Meta:
        model = ComplexityParameter
        fields = [
            'number_of_pages',
            'number_of_helix_v2_compatible',
            'number_of_helix_v2_non_compatible',
            'number_of_custom_components',
            'total_simple_components',
            'total_medium_components',
            'total_complex_components'
        ]
        
        widgets = {
            'number_of_pages': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '100'
            }),
            'number_of_helix_v2_compatible': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '50'
            }),
            'number_of_helix_v2_non_compatible': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '20'
            }),
            'number_of_custom_components': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '10'
            }),
            'total_simple_components': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '30'
            }),
            'total_medium_components': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '40'
            }),
            'total_complex_components': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '30'
            }),
        }
        
        labels = {
            'number_of_pages': 'Number of Pages',
            'number_of_helix_v2_compatible': 'Helix V2 Compatible Components',
            'number_of_helix_v2_non_compatible': 'Helix V2 Non-Compatible Components',
            'number_of_custom_components': 'Custom Components',
            'total_simple_components': 'Simple Complexity Components',
            'total_medium_components': 'Medium Complexity Components',
            'total_complex_components': 'Complex Complexity Components'
        }
        
        help_texts = {
            'number_of_pages': 'Base number of pages to consider for complexity calculation',
            'number_of_helix_v2_compatible': 'Number of components compatible with Helix V2',
            'number_of_helix_v2_non_compatible': 'Number of components not compatible with Helix V2',
            'number_of_custom_components': 'Number of custom components requiring special handling',
            'total_simple_components': 'Total count of components with simple complexity',
            'total_medium_components': 'Total count of components with medium complexity',
            'total_complex_components': 'Total count of components with complex complexity'
        }
