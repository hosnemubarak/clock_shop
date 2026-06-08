from functools import wraps
from django.core.exceptions import PermissionDenied

def staff_or_superuser_required(view_func):
    """
    Decorator for views that checks that the user is logged in
    and is either staff or superuser.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied
    return _wrapped_view
