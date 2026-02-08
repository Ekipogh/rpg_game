from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from typing import Optional, Tuple

from hero.models import Hero
from item.models import (
    Inventory, InventoryItem, Item, OffHand, Weapon, Armor,
    Consumable, Equipment, EquipmentSlot, EquipmentSlots, Accessory
)

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
        'level_requirement': getattr(item, 'level_requirement', 1),
    }

    # Add type-specific attributes and methods
    if isinstance(item, Weapon):
        item_info.update({
            'attack_bonus': item.attack_bonus,
            'accuracy_bonus': item.accuracy_bonus,
            'weapon_type': item.weapon_type,
            'equipment_slot': item.equipment_slot,
            'attack_description': f"ATK +{item.attack_bonus}, ACC +{item.accuracy_bonus}",
            'can_attack': True,
            'icon_class': 'fas fa-sword',
            'stat_color': 'text-danger',  # Red for attack
        })

    elif isinstance(item, Armor):
        item_info.update({
            'defense_bonus': item.defense_bonus,
            'health_bonus': item.health_bonus,
            'armor_type': item.armor_type,
            'equipment_slot': item.equipment_slot,
            'defense_description': f"DEF +{item.defense_bonus}, HP +{item.health_bonus}",
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


def get_or_create_inventory(hero: Hero) -> Inventory:
    """Get or create an inventory for the given hero"""
    if hasattr(hero, 'inventory') and hero.inventory:
        return hero.inventory

    inventory = Inventory.objects.create()
    hero.inventory = inventory  # type: ignore
    hero.save(update_fields=['inventory'])
    return inventory


def remove_inventory_item(inventory: Inventory, item: Item) -> Optional[int]:
    """Remove an item from inventory, decrementing quantity or deleting if last one"""
    inventory_item = InventoryItem.objects.filter(inventory=inventory, item=item).first()
    if not inventory_item:
        return None

    if inventory_item.quantity > 1:
        inventory_item.quantity -= 1
        inventory_item.save(update_fields=['quantity'])
        return inventory_item.quantity

    inventory_item.delete()
    return 0


def add_inventory_item(inventory: Inventory, item: Item) -> None:
    """Add an item to inventory, incrementing quantity if it already exists"""
    inventory_item, created = InventoryItem.objects.get_or_create(
        inventory=inventory, item=item, defaults={'quantity': 1}
    )
    if not created:
        inventory_item.quantity += 1
        inventory_item.save(update_fields=['quantity'])


def serialize_inventory_item(item: Item) -> dict:
    """Serialize item to JSON format for API responses"""
    # Determine category based on item type
    category_map = {
        Weapon: 'weapon',
        Armor: 'armor',
        Accessory: 'accessory',
        Consumable: 'consumable',
        OffHand: 'offhand',
    }
    category = next((cat for item_type, cat in category_map.items() if isinstance(item, item_type)), 'other')

    # Base payload common to all items
    payload = {
        'id': item.id,
        'name': item.name,
        'description': item.description or '',
        'value': item.value,
        'category': category,
        'item_type': item.item_type,
        'equipment_slot': getattr(item, 'equipment_slot', ''),
    }

    # Add type-specific attributes
    if isinstance(item, Weapon):
        payload.update({
            'attack_bonus': item.attack_bonus,
            'accuracy_bonus': item.accuracy_bonus,
            'weapon_type': item.weapon_type,
        })
    elif isinstance(item, Armor):
        payload.update({
            'defense_bonus': item.defense_bonus,
            'health_bonus': item.health_bonus,
            'armor_type': item.armor_type,
        })
    elif isinstance(item, Accessory):
        payload.update({
            'critical_bonus': item.critical_bonus,
            'accessory_type': item.accessory_type,
        })
    elif isinstance(item, OffHand):
        payload.update({
            'block': item.block,
            'shield_type': item.shield_type,
        })
    elif isinstance(item, Consumable):
        payload.update({
            'heal_amount': item.heal_amount,
            'mana_restore': item.mana_restore,
            'duration': item.duration,
        })

    return payload


def use_item_api(request, item_id):
    """
    API endpoint that handles polymorphic item usage
    Different item types will have different effects
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # Get the polymorphic item
    item = get_object_or_404(Item, id=item_id)

    # Get hero from session
    hero_id = request.session.get('hero_id')
    if not hero_id:
        return JsonResponse({'error': 'No hero selected'}, status=400)

    hero = get_object_or_404(Hero, id=hero_id)

    # Polymorphic usage - different behavior for each type!
    try:
        # Check if item is in inventory for equipment items
        if isinstance(item, (Weapon, Armor, OffHand)) or (
            getattr(item, 'equipment_slot', None) == EquipmentSlots.ACCESSORY.value
        ):
            inventory = get_or_create_inventory(hero)
            if not InventoryItem.objects.filter(inventory=inventory, item=item).exists():
                return JsonResponse({'error': 'Item not found in inventory'}, status=400)

        slot_type = None
        did_change = False
        unequipped_item = None
        action_type = 'used'

        # Equipment handling with type mapping
        equipment_handlers = {
            Weapon: (equip_weapon, EquipmentSlots.WEAPON.value),
            Armor: (equip_armor, EquipmentSlots.ARMOR.value),
        }

        # Check if item is equipment type
        handler_info = next(
            ((handler, slot) for item_type, (handler, slot) in equipment_handlers.items() if isinstance(item, item_type)),
            None
        )

        if handler_info:
            handler, slot_type = handler_info
            result, unequipped_item, did_change = handler(hero, item)
            action_type = 'equipped'
        elif isinstance(item, OffHand) or (getattr(item, 'equipment_slot', None) == EquipmentSlots.ACCESSORY.value):
            result, unequipped_item, did_change = equip_accessory(hero, item)
            action_type = 'equipped'
            slot_type = EquipmentSlots.ACCESSORY.value
        elif isinstance(item, Consumable):
            result = item.use(hero)  # Uses the polymorphic method
            action_type = 'consumed'
        else:
            result = f"Used {item.name}"

        # Remove from inventory if equipped successfully
        remaining_quantity = None
        if action_type == 'equipped' and did_change:
            inventory = get_or_create_inventory(hero)
            remaining_quantity = remove_inventory_item(inventory, item)
            if remaining_quantity is None:
                return JsonResponse({'error': 'Item not found in inventory'}, status=400)

            if unequipped_item and unequipped_item.id != item.id:
                add_inventory_item(inventory, unequipped_item)

        return JsonResponse({
            'success': True,
            'message': result,
            'action_type': action_type,
            'slot_type': slot_type,
            'item_type': item.__class__.__name__,
            'did_change': did_change,
            'remaining_quantity': remaining_quantity,
            'unequipped_item': serialize_inventory_item(unequipped_item) if unequipped_item else None,
            'hero_health': hero.current_health,
            'hero_max_health': hero.max_health,
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def _get_or_create_equipment_with_slots(hero: Hero) -> Equipment:
    """Helper function to get or create equipment and ensure all slots exist"""
    equipment, created = Equipment.objects.get_or_create(hero=hero)
    if created:
        # Create equipment slots if equipment was just created
        for slot_choice in EquipmentSlots:
            EquipmentSlot.objects.create(equipment=equipment, slot=slot_choice.value, item=None)
    return equipment


def equip_weapon(hero: Hero, weapon: Weapon) -> Tuple[str, Optional[Item], bool]:
    """Handle weapon-specific equipping logic"""
    # Check if hero can use this weapon type
    if weapon.hero_class_restriction and weapon.hero_class_restriction != hero.hero_class:
        return f"Only {weapon.hero_class_restriction.name}s can use this weapon!", None, False

    if weapon.level_requirement > hero.level:
        return f"Level {weapon.level_requirement} required to equip this weapon!", None, False

    # Get or create equipment for hero
    equipment = _get_or_create_equipment_with_slots(hero)

    # Get the weapon slot
    weapon_slot, _ = EquipmentSlot.objects.get_or_create(
        equipment=equipment,
        slot=EquipmentSlots.WEAPON.value,
        defaults={'item': None}
    )

    # Check if weapon is already equipped
    old_weapon = weapon_slot.item
    if old_weapon and old_weapon.id == weapon.id:
        return f"{weapon.name} is already equipped.", None, False

    # Equip new weapon
    weapon_slot.item = weapon
    weapon_slot.save()

    result = f"Equipped {weapon.name}! Attack power increased by {weapon.attack_bonus}!"
    if old_weapon:
        result += f" (Unequipped {old_weapon.name})"

    return result, old_weapon, True


def equip_armor(hero: Hero, armor: Armor) -> Tuple[str, Optional[Item], bool]:
    """Handle armor-specific equipping logic"""
    # Check class restrictions
    if armor.hero_class_restriction and armor.hero_class_restriction != hero.hero_class:
        return f"Only {armor.hero_class_restriction.name}s can wear this armor!", None, False

    if armor.level_requirement > hero.level:
        return f"Level {armor.level_requirement} required to equip this armor!", None, False

    # Get or create equipment for hero
    equipment = _get_or_create_equipment_with_slots(hero)

    # Get the armor slot
    armor_slot, _ = EquipmentSlot.objects.get_or_create(
        equipment=equipment,
        slot=EquipmentSlots.ARMOR.value,
        defaults={'item': None}
    )

    # Check if armor is already equipped
    old_armor = armor_slot.item
    if old_armor and old_armor.id == armor.id:
        return f"{armor.name} is already equipped.", None, False

    # Equip new armor
    armor_slot.item = armor
    armor_slot.save()

    result = f"Equipped {armor.name}! Defense increased by {armor.defense_bonus}!"
    if old_armor:
        result += f" (Unequipped {old_armor.name})"

    return result, old_armor, True


def equip_accessory(hero: Hero, accessory: Item) -> Tuple[str, Optional[Item], bool]:
    """Handle accessory-specific equipping logic"""
    # Check class restrictions if any
    if hasattr(accessory, 'hero_class_restriction') and accessory.hero_class_restriction and accessory.hero_class_restriction != hero.hero_class:
        return f"Only {accessory.hero_class_restriction.name}s can use this accessory!", None, False

    if hasattr(accessory, 'level_requirement') and accessory.level_requirement > hero.level:
        return f"Level {accessory.level_requirement} required to equip this accessory!", None, False

    # Get or create equipment for hero
    equipment = _get_or_create_equipment_with_slots(hero)

    # Get the accessory slot
    accessory_slot, _ = EquipmentSlot.objects.get_or_create(
        equipment=equipment,
        slot=EquipmentSlots.ACCESSORY.value,
        defaults={'item': None}
    )

    # Check if accessory is already equipped
    old_accessory = accessory_slot.item
    if old_accessory and old_accessory.id == accessory.id:
        return f"{accessory.name} is already equipped.", None, False

    # Equip new accessory
    accessory_slot.item = accessory
    accessory_slot.save()

    result = f"Equipped {accessory.name}!"
    critical_bonus = getattr(accessory, 'critical_bonus', 0)
    block = getattr(accessory, 'block', 0)

    if critical_bonus > 0:
        result += f" Critical chance increased by {critical_bonus}%!"
    elif block > 0:
        result += f" Defense increased by {block}!"

    if old_accessory:
        result += f" (Unequipped {old_accessory.name})"

    return result, old_accessory, True


def inventory_view(request):
    """
    Display the hero's inventory, categorized by item type, and currently equipped items.
    """
    # Get hero from session
    hero_id = request.session.get('hero_id')
    equipped_items = {}

    if not hero_id:
        inventory_items = []
        # For demo purposes, create mock inventory items
        for item in Item.objects.all():
            inventory_items.append(type('MockInventoryItem', (), {'item': item, 'quantity': 1})())
    else:
        hero = get_object_or_404(Hero, id=hero_id)
        inventory = hero.inventory
        inventory_items = [] if inventory is None else inventory.all()

        # Get equipped items
        equipment = _get_or_create_equipment_with_slots(hero)
        equipped_slots = EquipmentSlot.objects.filter(equipment=equipment)
        equipped_items = {slot.slot: slot.item for slot in equipped_slots if slot.item}

    # Get IDs of equipped items to filter them out of inventory display
    equipped_item_ids = {item.id for item in equipped_items.values()}

    # Categorize items automatically using polymorphic types
    categories = {
        'weapons': [],
        'armor': [],
        'accessories': [],
        'consumables': [],
        'offhands': [],
        'other_items': []
    }
    item_count = 0
    items_value = 0

    for inventory_item in inventory_items:
        item = inventory_item.item
        quantity = inventory_item.quantity

        # Skip items that are currently equipped
        if item.id in equipped_item_ids:
            continue

        # Categorize item by type
        if isinstance(item, Weapon):
            categories['weapons'].append(item)
        elif isinstance(item, Armor):
            categories['armor'].append(item)
        elif isinstance(item, Accessory):
            categories['accessories'].append(item)
        elif isinstance(item, Consumable):
            categories['consumables'].append(item)
        elif isinstance(item, OffHand):
            categories['offhands'].append(item)
        else:
            categories['other_items'].append(item)

        item_count += quantity
        items_value += item.value * quantity

    context = {
        **categories,
        'total_items': item_count,
        'total_value': items_value,
        'equipped_items': equipped_items,
        'equipment_slots': list(EquipmentSlots),
    }

    return render(request, 'item/inventory.html', context)


def unequip_item_api(request, slot_type):
    """
    API endpoint to unequip an item from a specific slot
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # Get hero from session
    hero_id = request.session.get('hero_id')
    if not hero_id:
        return JsonResponse({'error': 'No hero selected'}, status=400)

    hero = get_object_or_404(Hero, id=hero_id)

    try:
        equipment = _get_or_create_equipment_with_slots(hero)
        equipment_slot = EquipmentSlot.objects.get(equipment=equipment, slot=slot_type)

        if equipment_slot.item:
            unequipped_item = equipment_slot.item
            equipment_slot.item = None
            equipment_slot.save()

            inventory = get_or_create_inventory(hero)
            add_inventory_item(inventory, unequipped_item)

            return JsonResponse({
                'success': True,
                'message': f'Unequipped {unequipped_item.name} from {slot_type} slot',
                'slot_type': slot_type,
                'unequipped_item': serialize_inventory_item(unequipped_item),
            })
        else:
            return JsonResponse({'error': f'No item equipped in {slot_type} slot'}, status=400)

    except Equipment.DoesNotExist:
        return JsonResponse({'error': 'No equipment found for hero'}, status=400)
    except EquipmentSlot.DoesNotExist:
        return JsonResponse({'error': f'Invalid slot type: {slot_type}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
