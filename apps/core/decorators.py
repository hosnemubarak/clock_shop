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
from functools import wraps

def custom_user_passes_test(test_func):
    """
    Custom decorator that redirects unauthorized authenticated users to an
    'unauthorized' page instead of throwing a 403 or redirecting to login.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            
            if test_func(request.user):
                return view_func(request, *args, **kwargs)
                
            # Authenticated but unauthorized -> Show access denied page
            return redirect('core:unauthorized')
        return _wrapped_view
    return decorator

admin_required = custom_user_passes_test(is_admin)
manager_required = custom_user_passes_test(is_manager)
cashier_required = custom_user_passes_test(is_cashier)

def has_permission(perm):
    """
    Decorator for views that checks whether a user has a particular permission enabled,
    redirecting to the unauthorized page if necessary.
    """
    def check_perms(user):
        if user.is_superuser:
            return True
        if isinstance(perm, str):
            perms = (perm,)
        else:
            perms = perm
        return user.has_perms(perms)
    return custom_user_passes_test(check_perms)
