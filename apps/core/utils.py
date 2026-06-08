from .models import AuditLog


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def create_audit_log(request, action, instance, changes=None):
    """Create an audit log entry."""
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        model_name=instance.__class__.__name__,
        object_id=instance.pk,
        object_repr=str(instance)[:255],
        changes=changes or {},
        ip_address=get_client_ip(request),
    )


def verify_recaptcha(token, ip=None):
    """
    Verify reCAPTCHA token with Google API.
    Returns True if valid, False otherwise.
    """
    import urllib.request
    import urllib.parse
    import json
    from django.conf import settings

    if not getattr(settings, 'RECAPTCHA_ENABLED', False):
        return True
        
    if not token:
        return False
        
    secret_key = getattr(settings, 'RECAPTCHA_SECRET_KEY', None)
    if not secret_key:
        return False
        
    url = "https://www.google.com/recaptcha/api/siteverify"
    params = {
        'secret': secret_key,
        'response': token,
    }
    if ip:
        params['remoteip'] = ip
        
    data = urllib.parse.urlencode(params).encode('utf-8')
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode())
            return result.get('success', False) and result.get('score', 0.0) >= 0.5
    except Exception:
        return False

