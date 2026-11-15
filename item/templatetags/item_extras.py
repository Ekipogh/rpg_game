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


@register.filter
def status_label(value):
    return str(value).replace("_", " ").title()


@register.filter
def accessory_stats(item):
    stats = []
    for field, label in (("defense_bonus", "DEF"), ("speed_bonus", "SPD"),
                         ("magic_bonus", "MAG"), ("magic_defense_bonus", "MDEF"),
                         ("critical_bonus", "CRIT")):
        value = getattr(item, field, 0)
        if value > 0:
            stats.append(f"{label} +{value}{'%' if field == 'critical_bonus' else ''}")
    for status, percent in (item.status_resistances or {}).items():
        stats.append(f"{status_label(status)} Resistance {percent}%")
    accessory_type = (item.accessory_type or "ring").title()
    return f"{', '.join(stats)} • {accessory_type}" if stats else accessory_type
