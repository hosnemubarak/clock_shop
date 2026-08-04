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

from django.shortcuts import redirect

def custom_user_passes_test(test_func):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"{settings.LOGIN_URL}?next={request.path}")
            if test_func(request.user):
                return view_func(request, *args, **kwargs)
            return redirect('core:unauthorized')
        return _wrapped_view
    return decorator

admin_required = custom_user_passes_test(is_admin)
manager_required = custom_user_passes_test(is_manager)
cashier_required = custom_user_passes_test(is_cashier)
