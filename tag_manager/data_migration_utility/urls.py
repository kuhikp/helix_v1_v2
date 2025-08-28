from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.data_migration_create, name='data_migration_create'),
    path('list/', views.data_migration_list, name='data_migration_list'),
    path('edit/<int:pk>/', views.data_migration_edit, name='data_migration_edit'),
    path('delete/<int:pk>/', views.data_migration_delete, name='data_migration_delete'),
    path('detail/<int:pk>/', views.data_migration_detail, name='data_migration_detail'),
    path('clear-embeddings/', views.clear_embeddings, name='clear_embeddings'),
]
