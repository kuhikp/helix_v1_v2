from django.urls import path
from . import views
from .views import export_tag_mapper_records, export_non_tag_mapper_records, export_non_tag_mapper_v1_records, export_non_tag_mapper_v1_records_with_repo, export_all_tags_with_mapped_attributes_and_repo

urlpatterns = [
    path('', views.tag_list, name='tag_list'),
    path('create/', views.tag_create, name='tag_create'),
    path('<int:pk>/edit/', views.tag_edit, name='tag_edit'),
    path('<int:pk>/delete/', views.tag_delete, name='tag_delete'),
    path('tags/by-version/', views.tag_list_by_version, name='tag_list_by_version'),
    path('tags-extractor/', views.tags_extractor_list, name='tags_extractor_list'),
    path('tags-extractor/create/', views.tags_extractor_create, name='tags_extractor_create'),
    path('tags-extractor/<int:extractor_id>/', views.tags_extractor_detail, name='tags_extractor_detail'),
    path('tags-extractor/process/<int:extractor_id>/', views.process_pending_items, name='process_pending_items'),
    path('tag-mapper/', views.tag_mapper, name='tag_mapper'),
    path('export-v1-tags/', views.export_v1_tags, name='export_v1_tags'),
    path('export-v2-tags/', views.export_v2_tags, name='export_v2_tags'),
    path('auto-map-v1-to-v2/', views.auto_map_v1_to_v2_tags, name='auto_map_v1_to_v2_tags'),
    path('export_tag_mapper_records/', export_tag_mapper_records, name='export_tag_mapper_records'),
    path('export_non_tag_mapper_records/', export_non_tag_mapper_records, name='export_non_tag_mapper_records'),
    path('export_non_tag_mapper_v1_records/', export_non_tag_mapper_v1_records, name='export_non_tag_mapper_v1_records'),
    path('export_non_tag_mapper_v1_records_with_repo/', export_non_tag_mapper_v1_records_with_repo, name='export_non_tag_mapper_v1_records_with_repo'),
    path('export_all_tags_with_mapped_attributes_and_repo/', export_all_tags_with_mapped_attributes_and_repo, name='export_all_tags_with_mapped_attributes_and_repo'),
    
    # Complexity Mapping URLs
    path('complexity-mapping/', views.complexity_mapping_upload, name='complexity_mapping_upload'),
    path('complexity-mapping/template/', views.download_complexity_mapping_template, name='download_complexity_mapping_template'),
    
    # Complexity Parameter Configuration URLs
    path('complexity-parameter-config/', views.complexity_parameter_config, name='complexity_parameter_config'),
]
