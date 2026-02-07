from django import template

register = template.Library()

@register.filter
def lookup(dictionary, key):
    """Custom template filter to look up dictionary values by key"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None