from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse

from hero.models import Hero
from item.models import Inventory, Item, OffHand, Weapon, Armor, Consumable

# Create your views here.

def item_detail(request, item_id):
    """
    Single view that displays different information based on item type.
    With polymorphic models, the item will automatically be the correct subclass!
    """
    # This returns the actual subclass (Weapon, Armor, Consumable) automatically!
    item = get_object_or_404(Item, id=item_id)

    # Gather type-specific information
    item_info = {
        'item': item,
        'item_type': item.__class__.__name__,
        'item_type_lower': item.__class__.__name__.lower(),
    }

    # Add type-specific attributes and methods
    if isinstance(item, Weapon):
        item_info.update({
            'damage': item.damage,
            'weapon_type': item.weapon_type,
            'equipment_slot': item.equipment_slot,
            'attack_description': f"Deals {item.damage} damage",
            'can_attack': True,
            'icon_class': 'fas fa-sword',
            'stat_color': 'text-danger',  # Red for damage
        })

    elif isinstance(item, Armor):
        item_info.update({
            'defense': item.defense,
            'armor_type': item.armor_type,
            'equipment_slot': item.equipment_slot,
            'defense_description': f"Provides {item.defense} defense",
            'can_equip': True,
            'icon_class': 'fas fa-shield-alt',
            'stat_color': 'text-primary',  # Blue for defense
        })

    elif isinstance(item, Consumable):
        item_info.update({
            'heal_amount': item.heal_amount,
            'mana_restore': item.mana_restore,
            'duration': item.duration,
            'use_description': f"Restores {item.heal_amount} HP and {item.mana_restore} MP",
            'can_consume': True,
            'icon_class': 'fas fa-flask',
            'stat_color': 'text-success',  # Green for healing
        })

    # Add common display logic
    item_info['rarity_color'] = get_rarity_color(item.value)
    item_info['formatted_value'] = format_currency(item.value)

    return render(request, 'item/detail.html', item_info)


def get_rarity_color(value):
    """Determine rarity color based on item value"""
    if value >= 1000:
        return 'text-warning'  # Gold for legendary
    elif value >= 500:
        return 'text-info'     # Cyan for epic
    elif value >= 100:
        return 'text-success'  # Green for rare
    else:
        return 'text-secondary'  # Gray for common


def format_currency(value):
    """Format currency with gold symbol"""
    return f"{value:,} 🪙"


def use_item_api(request, item_id):
    """
    API endpoint that handles polymorphic item usage
    Different item types will have different effects
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # Get the polymorphic item
    item = get_object_or_404(Item, id=item_id)

    # Get hero from session (assuming you have hero management)
    hero_id = request.session.get('hero_id')
    if not hero_id:
        return JsonResponse({'error': 'No hero selected'}, status=400)

    from hero.models import Hero
    hero = get_object_or_404(Hero, id=hero_id)

    # Polymorphic usage - different behavior for each type!
    try:
        if isinstance(item, Weapon):
            result = equip_weapon(hero, item)
            action_type = 'equipped'

        elif isinstance(item, Armor):
            result = equip_armor(hero, item)
            action_type = 'equipped'

        elif isinstance(item, Consumable):
            result = item.use(hero)  # Uses the polymorphic method
            action_type = 'consumed'

        else:
            result = f"Used {item.name}"
            action_type = 'used'

        return JsonResponse({
            'success': True,
            'message': result,
            'action_type': action_type,
            'item_type': item.__class__.__name__,
            'hero_health': hero.current_health,
            'hero_max_health': hero.max_health,
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def equip_weapon(hero, weapon):
    """Handle weapon-specific equipping logic"""
    # Check if hero can use this weapon type
    if weapon.hero_class_restriction and weapon.hero_class_restriction != hero.hero_class:
        return f"Only {weapon.hero_class_restriction.name}s can use this weapon!"

    # TODO: Check if weapon slot is available, unequip current weapon, etc.
    return f"Equipped {weapon.name}! Attack power increased by {weapon.damage}!"


def equip_armor(hero, armor):
    """Handle armor-specific equipping logic"""
    # Check class restrictions
    if armor.hero_class_restriction and armor.hero_class_restriction != hero.hero_class:
        return f"Only {armor.hero_class_restriction.name}s can wear this armor!"

    # TODO: Check if armor slot is available, unequip current armor, etc.
    return f"Equipped {armor.name}! Defense increased by {armor.defense}!"


def inventory_view(request):
    """
    Display the hero's inventory, categorized by item type.
    """
    # Get hero from session
    hero_id = request.session.get('hero_id')
    if not hero_id:
        inventory_items = []
        # For demo purposes, create mock inventory items
        for item in Item.objects.all():
            inventory_items.append(type('MockInventoryItem', (), {'item': item, 'quantity': 1})())
    else:
        hero = get_object_or_404(Hero, id=hero_id)
        inventory = hero.inventory
        if inventory is None:
            inventory_items = []
        else:
            inventory_items = inventory.all()  # Assuming Inventory has a method to get all items

    # Categorize items automatically using polymorphic types
    weapons = []
    offhands = []
    armor = []
    consumables = []
    other_items = []

    item_count = 0
    items_value = 0

    for inventory_item in inventory_items:
        item = inventory_item.item
        quantity = inventory_item.quantity
        if isinstance(item, Weapon):
            weapons.append(item)
        elif isinstance(item, Armor):
            armor.append(item)
        elif isinstance(item, Consumable):
            consumables.append(item)
        elif isinstance(item, OffHand):
            offhands.append(item)
        else:
            other_items.append(item)
        item_count += quantity
        items_value += item.value * quantity

    context = {
        'weapons': weapons,
        'armor': armor,
        'consumables': consumables,
        'other_items': other_items,
        'total_items': item_count,
        'total_value': items_value,
    }

    return render(request, 'item/inventory.html', context)
