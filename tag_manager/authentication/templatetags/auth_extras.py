from django import template
from django.conf import settings

register = template.Library()

MENU_PERMISSIONS = {
    'dashboard': ['admin', 'tag_manager', 'tag_viewer'],
    'users': ['admin'],
    'tags': ['admin', 'tag_manager', 'tag_viewer'],
    'tags_extractor': ['admin', 'tag_manager'],
    'tags_listing': ['admin', 'tag_manager', 'tag_viewer'],
    'mapper': ['admin', 'tag_manager'],
    'tag_mapper': ['admin', 'tag_manager'],
    'migration_list': ['admin', 'tag_manager'],
    'knowledge_base': ['admin', 'tag_manager'],
    'rag_system': ['admin', 'tag_manager'],
    'sites': ['admin', 'tag_manager'],
    'api': ['admin', 'tag_manager', 'tag_viewer'],
}

ROLE_PERMISSIONS = {
    'admin': [
        'view_all', 'edit_all', 'delete_all', 'manage_users',
        'manage_sites', 'manage_tags', 'manage_migrations'
    ],
    'tag_manager': [
        'view_all', 'edit_tags', 'manage_tags', 'manage_migrations'
    ],
    'tag_viewer': ['view_all'],
}

@register.simple_tag(takes_context=True)
def can_access_menu(context, menu_name):
    """
    Check if user has permission to access a specific menu.
    Returns True if user has permission, False otherwise.
    """
    MENU_PERMISSIONS = {
        'dashboard': ['admin', 'tag_manager', 'tag_viewer'],
        'users': ['admin'],
        'tags': ['admin', 'tag_manager', 'tag_viewer'],
        'tags_extractor': ['admin', 'tag_manager'],
        'tags_listing': ['admin', 'tag_manager', 'tag_viewer'],
        'mapper': ['admin', 'tag_manager'],
        'tag_mapper': ['admin', 'tag_manager'],
        'migration_list': ['admin', 'tag_manager'],
        'knowledge_base': ['admin', 'tag_manager'],
        'sites': ['admin', 'tag_manager'],
        'api': ['admin', 'tag_manager', 'tag_viewer'],
    }
    
    """
    Check if user has permission to access a specific menu.
    Usage: {% can_access_menu 'menu_name' as show_menu %}
    """
    user = context['user']
    if not user.is_authenticated:
        return False
        
    if user.is_superuser:
        return True
        
    allowed_roles = MENU_PERMISSIONS.get(menu_name, [])
    return hasattr(user, 'role') and user.role in allowed_roles

@register.filter(name='has_permission')
def has_permission(user, permission):
    """
    Check if user has a specific permission.
    Usage: {% if user|has_permission:'permission_name' %}
    """
    if not user.is_authenticated:
        return False
        
    if user.is_superuser:
        return True
        
    if not hasattr(user, 'role'):
        return False
        
    allowed_permissions = ROLE_PERMISSIONS.get(user.role, [])
    return permission in allowed_permissions

@register.simple_tag(takes_context=True)
def get_menu_class(context, menu_name):
    """
    Get the CSS class for a menu item based on current path and permissions.
    Usage: {% get_menu_class 'menu_name' as menu_class %}
    """
    request = context['request']
    is_active = menu_name.lower() in request.path.lower()
    return 'active' if is_active else ''
