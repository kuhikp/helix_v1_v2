"""
URL configuration for tag_manager project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

def root_redirect(request):
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('admin_dashboard')
        elif request.user.role == 'tag_manager':
            return redirect('tag_list')
    return redirect('login')

urlpatterns = [
    path('', root_redirect, name='root_redirect'),
    path('admin/', admin.site.urls),
    path('auth/', include('authentication.urls')),
    path('tags/', include('tag_manager_component.urls')),
    path('sites/', include('site_manager.urls')),
    path('migrations/', include('data_migration_utility.urls')),
    path('api/', include('api_component.urls')),
]

# Serve static and media files during development
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
urlpatterns += staticfiles_urlpatterns()

handler404 = 'tag_manager.views.custom_404_view'
handler500 = 'tag_manager.views.custom_500_view'
handler403 = 'tag_manager.views.custom_error_view'
handler400 = 'tag_manager.views.custom_error_view'
    
