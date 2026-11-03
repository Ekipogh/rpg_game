"""Atomic resource recovery; never write stale hero objects."""
from django.db.models import F
from django.db.models.functions import Least

from .models import Hero


def restore_resources(hero_id, health_amount=0, mana_amount=0):
    if any(type(amount) is not int or amount < 0 for amount in (health_amount, mana_amount)):
        raise ValueError('Recovery amounts must be nonnegative integers.')
    updates = {}
    if health_amount:
        updates['current_health'] = Least(F('max_health'), F('current_health') + health_amount)
    if mana_amount:
        updates['current_mana'] = Least(F('max_mana'), F('current_mana') + mana_amount)
    if not updates:
        return 0
    return Hero.objects.filter(pk=hero_id, is_in_combat=False).update(**updates)
