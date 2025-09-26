from django.urls import path
from . import views

urlpatterns = [
    # Data Migration URLs
    path('create/', views.data_migration_create, name='data_migration_create'),
    path('list/', views.data_migration_list, name='data_migration_list'),
    path('edit/<int:pk>/', views.data_migration_edit, name='data_migration_edit'),
    path('delete/<int:pk>/', views.data_migration_delete, name='data_migration_delete'),
    path('detail/<int:pk>/', views.data_migration_detail, name='data_migration_detail'),
    path('clear-embeddings/', views.clear_embeddings, name='clear_embeddings'),
    
    # Knowledge Base URLs
    path('knowledge-base/', views.knowledge_base_list, name='knowledge_base_list'),
    path('knowledge-base/create/', views.knowledge_base_create, name='knowledge_base_create'),
    path('knowledge-base/<int:pk>/', views.knowledge_base_detail, name='knowledge_base_detail'),
    path('knowledge-base/<int:pk>/edit/', views.knowledge_base_edit, name='knowledge_base_edit'),
    path('knowledge-base/<int:pk>/delete/', views.knowledge_base_delete, name='knowledge_base_delete'),
    
    # RAG System Management URLs
    path('rag-system/', views.rag_system_status, name='rag_system_status'),
    path('rag-system/update/', views.update_rag_system, name='update_rag_system'),
    path('rag-system/reset/', views.reset_rag_system, name='reset_rag_system'),
    path('api/rag-system/', views.rag_system_api, name='rag_system_api'),
]
