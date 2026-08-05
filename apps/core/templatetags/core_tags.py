from django import template
from django.utils.safestring import mark_safe

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


@register.tag(name='capture')
def do_capture(parser, token):
    """Render a block once and store its HTML in a context variable.

    Enables passing markup (e.g. dropdown menu <li> items) into an {% include %}
    partial, which Django's include cannot otherwise accept.

    Usage:
        {% capture as row_menu %}
            <li><a class="dropdown-item" href="...">Edit</a></li>
        {% endcapture %}
        {% include 'includes/row_actions.html' with menu=row_menu %}
    """
    bits = token.split_contents()
    if len(bits) != 3 or bits[1] != 'as':
        raise template.TemplateSyntaxError("Usage: {% capture as <var> %}...{% endcapture %}")
    varname = bits[2]
    nodelist = parser.parse(('endcapture',))
    parser.delete_first_token()
    return CaptureNode(nodelist, varname)


class CaptureNode(template.Node):
    def __init__(self, nodelist, varname):
        self.nodelist = nodelist
        self.varname = varname

    def render(self, context):
        context[self.varname] = mark_safe(self.nodelist.render(context).strip())
        return ''

from apps.core.decorators import is_manager

@register.filter(name='is_manager')
def is_manager_filter(user):
    return is_manager(user)
