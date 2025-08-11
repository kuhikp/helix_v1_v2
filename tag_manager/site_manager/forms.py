from django import forms
from .models import SiteListDetails, SiteMetaDetails

class SiteListDetailsForm(forms.ModelForm):
    class Meta:
        model = SiteListDetails
        fields = ['website_url']

class SiteMetaDetailsForm(forms.ModelForm):
    class Meta:
        model = SiteMetaDetails
        fields = '__all__'
