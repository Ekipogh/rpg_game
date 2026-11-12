"""Item receipt and immediate effects, shared by grants and battle rewards."""
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Least

from .models import Instant, Inventory, InventoryItem


def _quantity(quantity):
    if type(quantity) is not int or quantity < 1:
        raise ValueError('Quantity must be a positive integer')


def _locked_hero(hero):
    # First statement is a write: select_for_update alone cannot lock SQLite.
    from hero.models import Hero
    if hero.pk is None or not Hero.objects.filter(pk=hero.pk).update(money=F('money')):
        raise ValueError('A saved hero is required')
    return Hero.objects.get(pk=hero.pk)


def _sync(hero, current):
    for field in ('current_health', 'current_mana', 'money', 'inventory_id'):
        setattr(hero, field, getattr(current, field))


@transaction.atomic
def apply_consumable_effects(hero, item, quantity=1):
    """Apply an effect without adding/removing inventory or saving stale hero data."""
    _quantity(quantity)
    for name in ('heal_amount', 'mana_restore', 'money_amount'):
        amount = getattr(item, name)
        if type(amount) is not int or amount < 0:
            raise ValueError(f'{name} must be a nonnegative integer')
    current = _locked_hero(hero)
    before = (current.current_health, current.current_mana, current.money)
    updates = {}
    if item.heal_amount:
        updates['current_health'] = Least(F('max_health'), F('current_health') + item.heal_amount * quantity)
    if item.mana_restore:
        updates['current_mana'] = Least(F('max_mana'), F('current_mana') + item.mana_restore * quantity)
    if item.money_amount:
        updates['money'] = F('money') + item.money_amount * quantity
    if updates:
        type(current).objects.filter(pk=current.pk).update(**updates)
        current.refresh_from_db()
    if not isinstance(item, Instant) and (current.current_health != before[0] or current.current_mana != before[1]):
        from battle.services import sync_consumable_resources
        sync_consumable_resources(current, item, before)
    _sync(hero, current)
    return {'health_change': current.current_health - before[0],
            'mana_change': current.current_mana - before[1],
            'money_change': current.money - before[2]}


@transaction.atomic
def receive_item(hero, item, quantity=1):
    """The receipt boundary: Instant items apply now; other items enter stock.

    A repeated call represents another grant. Idempotency belongs to the caller
    (for battle loot, the battle resolution transaction and resolved_at marker).
    """
    _quantity(quantity)
    if item.pk is None:
        raise ValueError('A saved item is required')
    item = item.get_real_instance()
    current = _locked_hero(hero)
    if isinstance(item, Instant):
        effects = apply_consumable_effects(current, item, quantity)
        _sync(hero, current)
        return effects
    if current.inventory_id is None:
        current.inventory = Inventory.objects.create()
        current.save(update_fields=['inventory'])
    stock, _ = InventoryItem.objects.get_or_create(inventory_id=current.inventory_id,
        item_id=item.pk, defaults={'quantity': 0})
    InventoryItem.objects.filter(pk=stock.pk).update(quantity=F('quantity') + quantity)
    _sync(hero, current)
    return {'health_change': 0, 'mana_change': 0, 'money_change': 0}
