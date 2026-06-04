from django.conf import settings as django_settings
from datetime import date


def get_system_settings():
    """Get system settings from database with env fallback."""
    try:
        from .models import SystemSettings
        db_settings = SystemSettings.get_settings()
        return db_settings
    except Exception:
        return None


def global_context(request):
    """Global context processor for all templates."""
    db_settings = get_system_settings()
    
    # Shop name: DB value or env fallback
    if db_settings and db_settings.shop_name:
        shop_name = db_settings.shop_name
    else:
        shop_name = getattr(django_settings, 'SHOP_NAME', 'Clock Shop')
    
    # Currency symbol: DB value or env fallback
    if db_settings and db_settings.currency_symbol:
        currency_symbol = db_settings.currency_symbol
    else:
        currency_symbol = getattr(django_settings, 'CURRENCY_SYMBOL', '৳')
    
    # Low stock threshold: DB value or env fallback
    if db_settings and db_settings.low_stock_threshold:
        low_stock_threshold = db_settings.low_stock_threshold
    else:
        low_stock_threshold = getattr(django_settings, 'LOW_STOCK_THRESHOLD', 5)
    
    # License expiry alert
    expiry_alert = None
    days_until_expiry = None
    if db_settings and db_settings.license_expiry_date:
        today = date.today()
        days_until_expiry = (db_settings.license_expiry_date - today).days
        alert_threshold = db_settings.alert_days_before_expiry or 30
        
        if days_until_expiry < 0:
            expiry_alert = {
                'type': 'danger',
                'message': f'⚠ Server/License has EXPIRED {abs(days_until_expiry)} days ago. Please renew immediately!',
                'days': days_until_expiry,
                'critical': True
            }
        elif days_until_expiry <= alert_threshold:
            expiry_alert = {
                'type': 'danger' if days_until_expiry <= 7 else 'warning',
                'message': f'⚠ Server validity will expire in {days_until_expiry} days. Please renew to avoid service interruption.',
                'days': days_until_expiry,
                'critical': days_until_expiry <= 7
            }
    
    return {
        'SHOP_NAME': shop_name,
        'CURRENCY_SYMBOL': currency_symbol,
        'LOW_STOCK_THRESHOLD': low_stock_threshold,
        'EXPIRY_ALERT': expiry_alert,
        'DAYS_UNTIL_EXPIRY': days_until_expiry,
    }
