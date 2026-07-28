from django import template

register = template.Library()

@register.filter
def has_active_filters(request):
    """
    Returns True if there are any GET parameters other than 'page'.
    Usage: {% if request|has_active_filters %}
    """
    if not hasattr(request, 'GET'):
        return False
        
    for key, value in request.GET.items():
        if key != 'page' and value:
            return True
    return False
