from django import template
from django.utils.safestring import mark_safe
from ..image_utils import product_image_url

register = template.Library()


@register.filter(name='product_image')
def product_image(product):
    """Returns image URL for a product — real image or SVG placeholder."""
    url = product_image_url(product)
    return url


@register.filter(name='product_image_attr')
def product_image_attr(product):
    """Returns image URL safe for use in HTML attributes (escaped)."""
    return product_image_url(product)


@register.simple_tag(takes_context=True)
def pagination_url(context, page):
    """Build a query string for a pagination link, preserving all GET params except 'page'."""
    request = context['request']
    params = request.GET.copy()
    params['page'] = str(page)
    return '?' + params.urlencode()
