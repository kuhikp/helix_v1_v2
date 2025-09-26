from django import forms
from .models import DataMigrationUtility, KnowledgeBase


class KnowledgeBaseForm(forms.ModelForm):
    """
    Form for creating and editing Knowledge Base entries.
    Only accessible to admin users.
    """
    
    class Meta:
        model = KnowledgeBase
        fields = ['title', 'component_name', 'v1_code', 'v2_code', 'description', 'tags', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter a descriptive title for this knowledge base entry'
            }),
            'component_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., helix-image, helix-accordion'
            }),
            'v1_code': forms.Textarea(attrs={
                'class': 'form-control code-editor',
                'rows': 10,
                'placeholder': 'Enter the V1 component code...',
                'data-language': 'html'
            }),
            'v2_code': forms.Textarea(attrs={
                'class': 'form-control code-editor',
                'rows': 10,
                'placeholder': 'Enter the V2 component code...',
                'data-language': 'html'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Optional description or notes about this migration pattern'
            }),
            'tags': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter tags separated by commas (e.g., image, responsive, layout)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }

    def clean_v1_code(self):
        """Validate V1 code field."""
        v1_code = self.cleaned_data['v1_code']
        if not v1_code.strip():
            raise forms.ValidationError("V1 code cannot be empty.")
        return v1_code.strip()

    def clean_v2_code(self):
        """Validate V2 code field."""
        v2_code = self.cleaned_data['v2_code']
        if not v2_code.strip():
            raise forms.ValidationError("V2 code cannot be empty.")
        return v2_code.strip()

    def clean_component_name(self):
        """Validate component name field."""
        component_name = self.cleaned_data['component_name']
        if not component_name.strip():
            raise forms.ValidationError("Component name cannot be empty.")
        return component_name.strip().lower()


class DataMigrationUtilityForm(forms.ModelForm):
    v1_body = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control code-editor',
            'rows': 8,
            'placeholder': 'Enter V1 HTML content...',
            'data-language': 'html'
        }),
        required=False
    )
    v1_css = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control code-editor',
            'rows': 6,
            'placeholder': 'Enter V1 CSS content...',
            'data-language': 'css'
        }),
        required=False
    )
    v1_js = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control code-editor',
            'rows': 6,
            'placeholder': 'Enter V1 JavaScript content...',
            'data-language': 'javascript'
        }),
        required=False
    )
    v2_body = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control code-editor',
            'rows': 8,
            'placeholder': 'V2 HTML content will be generated...',
            'data-language': 'html',
            'readonly': 'readonly'
        }),
        required=False
    )
    v2_css = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control code-editor',
            'rows': 6,
            'placeholder': 'V2 CSS content will be generated...',
            'data-language': 'css',
            'readonly': 'readonly'
        }),
        required=False
    )
    v2_js = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control code-editor',
            'rows': 6,
            'placeholder': 'V2 JavaScript content will be generated...',
            'data-language': 'javascript',
            'readonly': 'readonly'
        }),
        required=False
    )

    class Meta:
        model = DataMigrationUtility
        fields = ['v1_body', 'v1_css', 'v1_js', 'v2_body', 'v2_css', 'v2_js']

    def clean(self):
        cleaned_data = super().clean()
        v1_body = cleaned_data.get('v1_body')
        v1_css = cleaned_data.get('v1_css')
        v1_js = cleaned_data.get('v1_js')
        
        # Check if at least one V1 field has content
        if not any([v1_body, v1_css, v1_js]):
            raise forms.ValidationError(
                "At least one V1 component (HTML, CSS, or JavaScript) must be provided."
            )
            
        return cleaned_data
