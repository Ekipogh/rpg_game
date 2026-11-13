"""Persistent shop stock and atomic trading services."""
import random
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import Item, Weapon, Armor, Accessory, Consumable, Instant, InventoryItem, ShopState, ShopOffer
from .services import _locked_hero, receive_item


def eligible(item, hero):
    return (isinstance(item, (Weapon, Armor, Accessory, Consumable))
            and not isinstance(item, Instant)
            and not getattr(item, 'money_amount', 0)
            and item.value > 0
            and max(1, hero.level - 2) <= item.level_requirement <= hero.level
            and item.hero_class_restriction_id in (None, hero.hero_class_id))


def stale(shop, hero, now):
    return (shop.expires_at <= now or shop.level != hero.level
            or shop.hero_class_id_at_generation != hero.hero_class_id)


@transaction.atomic
def stock_for(hero):
    hero = _locked_hero(hero)
    now = timezone.now()
    shop, created = ShopState.objects.get_or_create(hero=hero, defaults={
        'expires_at': now, 'level': hero.level,
        'hero_class_id_at_generation': hero.hero_class_id})
    if created or stale(shop, hero, now):
        pool = [item for item in Item.objects.filter(
            Q(hero_class_restriction_id=hero.hero_class_id) | Q(hero_class_restriction__isnull=True),
            value__gt=0, level_requirement__gte=max(1, hero.level - 2),
            level_requirement__lte=hero.level) if eligible(item, hero)]
        random.shuffle(pool)
        selected = []
        for category in (Weapon, Armor, Accessory, Consumable):
            candidate = next((item for item in pool if isinstance(item, category)), None)
            if candidate:
                selected.append(candidate)
        selected.extend(item for item in pool if item not in selected)
        shop.offers.all().delete()
        ShopOffer.objects.bulk_create([ShopOffer(shop=shop, item=item, price=item.value,
            remaining=5 if isinstance(item, Consumable) else 1) for item in selected[:8]])
        shop.expires_at = now + timedelta(hours=1)
        shop.level = hero.level
        shop.hero_class_id_at_generation = hero.hero_class_id
        shop.save()
    return shop


def quantity_value(value):
    try:
        if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
            raise ValueError
        quantity = int(value)
        if not 1 <= quantity <= 2147483647:
            raise ValueError
        return quantity
    except (ValueError, TypeError):
        raise ValueError('Choose a positive whole quantity.') from None


@transaction.atomic
def buy(hero, offer_id, quantity):
    quantity = quantity_value(quantity)
    hero = _locked_hero(hero)
    if hero.is_in_combat:
        raise ValueError('Shopping is unavailable during combat.')
    offer = ShopOffer.objects.select_related('shop').filter(pk=offer_id, shop__hero=hero).first()
    if not offer or stale(offer.shop, hero, timezone.now()):
        raise ValueError('This offer has expired. Refresh the shop.')
    item = Item.objects.get(pk=offer.item_id)
    if not eligible(item, hero):
        raise ValueError('This item is no longer available for your hero.')
    if offer.remaining < quantity:
        raise ValueError('Not enough stock remains.')
    total = offer.price * quantity
    if hero.money < total:
        raise ValueError('Not enough money.')
    type(hero).objects.filter(pk=hero.pk).update(money=F('money') - total)
    ShopOffer.objects.filter(pk=offer.pk).update(remaining=F('remaining') - quantity)
    receive_item(hero, item, quantity)


@transaction.atomic
def sell(hero, item_id, quantity):
    quantity = quantity_value(quantity)
    hero = _locked_hero(hero)
    if hero.is_in_combat:
        raise ValueError('Shopping is unavailable during combat.')
    stock = InventoryItem.objects.filter(inventory_id=hero.inventory_id, item_id=item_id).first()
    if not stock or stock.quantity < quantity:
        raise ValueError('Not enough spare copies in inventory. Unequip equipped items first.')
    item = Item.objects.get(pk=item_id)
    price = max(0, item.value // 2)
    if not price:
        raise ValueError('This item has no sale value.')
    if stock.quantity == quantity:
        stock.delete()
    else:
        InventoryItem.objects.filter(pk=stock.pk).update(quantity=F('quantity') - quantity)
    type(hero).objects.filter(pk=hero.pk).update(money=F('money') + price * quantity)
