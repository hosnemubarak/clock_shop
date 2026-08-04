from django.contrib.auth.decorators import user_passes_test
from django.conf import settings

def is_admin(user):
    if not getattr(settings, 'ENABLE_RBAC', True):
        return user.is_authenticated and user.is_active
    return user.is_active and (user.is_superuser or user.groups.filter(name='Admin').exists())

def is_manager(user):
    if not getattr(settings, 'ENABLE_RBAC', True):
        return user.is_authenticated and user.is_active
    return user.is_active and (is_admin(user) or user.groups.filter(name='Manager').exists())

def is_cashier(user):
    if not getattr(settings, 'ENABLE_RBAC', True):
        return user.is_authenticated and user.is_active
    return user.is_active and (is_manager(user) or user.groups.filter(name='Cashier').exists())

admin_required = user_passes_test(is_admin)
manager_required = user_passes_test(is_manager)
cashier_required = user_passes_test(is_cashier)
