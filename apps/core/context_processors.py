from django.conf import settings as django_settings
from django.utils import timezone


def get_system_settings():
    """Get system settings from database with env fallback."""
    try:
        from .models import SystemSettings
        from django.db.utils import OperationalError, ProgrammingError
        db_settings = SystemSettings.get_settings()
        return db_settings
    except (OperationalError, ProgrammingError):
        return None


def global_context(request):
    """Global context processor for all templates."""
    db_settings = get_system_settings()
    
    # Shop name: DB value or env fallback
    if db_settings and db_settings.shop_name:
        shop_name = db_settings.shop_name
    else:
        shop_name = getattr(django_settings, 'SHOP_NAME', 'Clock Shop')
        
    # Shop address: DB value or env fallback
    if db_settings and db_settings.shop_address:
        shop_address = db_settings.shop_address
    else:
        shop_address = getattr(django_settings, 'SHOP_ADDRESS', '')
    
    # Shop logo
    shop_logo_url = None
    if db_settings and db_settings.shop_logo:
        shop_logo_url = db_settings.shop_logo.url
    
    
    # Currency symbol: DB value or env fallback
    if db_settings and db_settings.currency_symbol:
        currency_symbol = db_settings.currency_symbol
    else:
        currency_symbol = getattr(django_settings, 'CURRENCY_SYMBOL', '৳')
    
    # Low stock threshold: DB value or env fallback. Test against None, not
    # truthiness -- a configured threshold of 0 is a legitimate value.
    if db_settings and db_settings.low_stock_threshold is not None:
        low_stock_threshold = db_settings.low_stock_threshold
    else:
        low_stock_threshold = getattr(django_settings, 'LOW_STOCK_THRESHOLD', 5)
    
    # License expiry alert
    expiry_alert = None
    days_until_expiry = None
    if db_settings and db_settings.license_expiry_date:
        today = timezone.localdate()
        days_until_expiry = (db_settings.license_expiry_date - today).days
        alert_threshold = db_settings.alert_days_before_expiry
        if alert_threshold is None:
            alert_threshold = 30
        
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
    
    if db_settings:
        allow_walkin = db_settings.allow_walkin_customers
    else:
        allow_walkin = True
        
    # Check if system settings are configured
    settings_warning = False
    if not shop_name or shop_name == 'Clock Shop' or not shop_address:
        settings_warning = True
        
    return {
        'SHOP_NAME': shop_name,
        'SHOP_LOGO_URL': shop_logo_url,
        'SHOP_ADDRESS': shop_address,
        'CURRENCY_SYMBOL': currency_symbol,
        'LOW_STOCK_THRESHOLD': low_stock_threshold,
        'EXPIRY_ALERT': expiry_alert,
        'DAYS_UNTIL_EXPIRY': days_until_expiry,
        'ALLOW_WALKIN_CUSTOMERS': allow_walkin,
        'SETTINGS_WARNING': settings_warning,
    }
