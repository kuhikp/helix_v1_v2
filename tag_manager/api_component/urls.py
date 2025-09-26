
from django.urls import path
from .views import (
    MigrateV1ToV2View, 
    get_token_form,
    RAGMigrateV1ToV2View,
    RAGSearchView,
    RAGStatsView,
    RAGResetView
)

app_name = 'api_component'

urlpatterns = [
    path('api_component/', MigrateV1ToV2View.as_view(), name='api_component'),
    path('get_token/', get_token_form, name='get_token'),
    
    # RAG-based endpoints
    path('rag/migrate/', RAGMigrateV1ToV2View.as_view(), name='rag_migrate'),
    path('rag/search/', RAGSearchView.as_view(), name='rag_search'),
    path('rag/stats/', RAGStatsView.as_view(), name='rag_stats'),
    path('rag/reset/', RAGResetView.as_view(), name='rag_reset'),
]
