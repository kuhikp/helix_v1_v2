from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('tag-manager/dashboard/', views.tag_manager_dashboard, name='tag_manager_dashboard'),
    path('admin/users/create/', views.create_user, name='create_user'),
    path('admin/users/<int:user_id>/edit/', views.edit_user, name='edit_user'),
    path('admin/users/<int:user_id>/delete/', views.delete_user, name='delete_user'),
    path('admin/users/<int:user_id>/view/', views.view_user, name='view_user'),
]
