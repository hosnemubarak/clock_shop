from django.conf import settings


def global_context(request):
    """Global context processor for all templates."""
    return {
        'SHOP_NAME': getattr(settings, 'SHOP_NAME', 'Clock Shop'),
        'CURRENCY_SYMBOL': getattr(settings, 'CURRENCY_SYMBOL', '$'),
    }
