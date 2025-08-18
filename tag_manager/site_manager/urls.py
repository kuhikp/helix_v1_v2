from django.urls import path
from . import views

urlpatterns = [
    path('', views.site_list, name='site_list'),
    path('create/', views.site_create, name='site_create'),
    path('<int:pk>/edit/', views.site_edit, name='site_edit'),
    path('<int:pk>/delete/', views.site_delete, name='site_delete'),
    path('<int:site_id>/meta/', views.site_meta_list, name='site_meta_list'),
    path('<int:site_id>/meta/create/', views.site_meta_create, name='site_meta_create'),
    path('<int:site_id>/meta/<int:pk>/edit/', views.site_meta_edit, name='site_meta_edit'),
    path('<int:site_id>/meta/<int:pk>/delete/', views.site_meta_delete, name='site_meta_delete'),
    path('<int:site_id>/analyze/', views.analyze_sitemap, name='analyze_sitemap'),
    path('import-websites-csv/', views.import_websites_csv, name='import_websites_csv'),
    path('batch-analyze-sitemaps/', views.batch_analyze_sitemaps, name='batch_analyze_sitemaps'),
    path('batch-analysis-progress/', views.batch_analysis_progress, name='batch_analysis_progress'),
    path('batch-update-complexity/', views.batch_update_complexity, name='batch_update_complexity'),
    path('batch-complexity-progress/', views.batch_complexity_progress, name='batch_complexity_progress'),
    path('download-sites-import-template/', views.download_sites_import_template, name='download_sites_import_template'),
    path('export-sites-csv/', views.export_sites_csv, name='export_sites_csv'),
    path('cleanup-site-data/', views.cleanup_site_data, name='cleanup_site_data'),
]
