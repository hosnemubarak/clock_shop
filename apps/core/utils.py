from typing import Optional, Dict, Any
from django.core.paginator import Page, Paginator
from django.db import models, transaction, IntegrityError
from django.utils import timezone
from .models import AuditLog


def paginate(request: Any, queryset: Any, per_page: int = 25, page_param: str = 'page') -> Page:
    """Paginate a queryset using the request's page query param.

    Centralizes the repeated ``Paginator(qs, n)`` + ``get_page`` scaffolding in
    the function-based list views. ``get_page`` is used (not ``page``) so an
    invalid or out-of-range page falls back to a valid page instead of raising.
    """
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get(page_param))


def get_client_ip(request: Any) -> str:
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip


def create_audit_log(request: Any, action: str, instance: models.Model, changes: Optional[Dict[str, Any]] = None) -> None:
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


def save_with_sequential_number(instance: models.Model, field_name: str, prefix: str, *args: Any, **kwargs: Any) -> None:
    """
    Generate a unique sequential number with a retry loop and save the instance.
    Replaces identical save overrides across models.
    """
    if getattr(instance, field_name):
        super(instance.__class__, instance).save(*args, **kwargs)
        return

    model_class = instance.__class__
    today_prefix = f"{prefix}{timezone.localdate().strftime('%Y%m%d')}"
    attempts = 0
    
    while attempts < 10:
        last = model_class.objects.filter(
            **{f"{field_name}__startswith": today_prefix}
        ).order_by(f"-{field_name}").first()
        
        if last:
            last_num = int(getattr(last, field_name)[-4:])
            setattr(instance, field_name, f"{today_prefix}{last_num + 1:04d}")
        else:
            setattr(instance, field_name, f"{today_prefix}0001")
            
        try:
            with transaction.atomic():
                super(model_class, instance).save(*args, **kwargs)
            break
        except IntegrityError:
            attempts += 1
            if attempts >= 10:
                raise
