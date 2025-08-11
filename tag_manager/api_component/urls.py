from django.urls import path
from .views import MigrateV1ToV2View, get_token_form

urlpatterns = [
    path('api_component/', MigrateV1ToV2View.as_view(), name='api_component'),
    path('get_token/', get_token_form, name='get_token'),
]
