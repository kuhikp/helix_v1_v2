from django import forms
from .models import DataMigrationUtility

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
