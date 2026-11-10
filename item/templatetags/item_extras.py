from django import template

from game.currency import format_currency, render_currency

register = template.Library()

@register.filter
def lookup(dictionary, key):
    """Custom template filter to look up dictionary values by key"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

register.filter("currency", format_currency)

register.filter("currency_coins", render_currency)
