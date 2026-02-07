from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse

from hero.models import Hero
from item.models import Inventory, Item, OffHand, Weapon, Armor, Consumable, Equipment, EquipmentSlot, EquipmentSlots, Accessory

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

        elif isinstance(item, OffHand):
            # Treat OffHand as an accessory for backward compatibility
            result = equip_accessory(hero, item)
            action_type = 'equipped'

        elif hasattr(item, 'equipment_slot') and item.equipment_slot == EquipmentSlots.ACCESSORY.value:
            result = equip_accessory(hero, item)
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

    # Get or create equipment for hero
    equipment, created = Equipment.objects.get_or_create(hero=hero)
    if created:
        # Create equipment slots if equipment was just created
        for slot_choice in EquipmentSlots:
            EquipmentSlot.objects.create(equipment=equipment, slot=slot_choice.value, item=None)

    # Get the weapon slot
    weapon_slot, created = EquipmentSlot.objects.get_or_create(
        equipment=equipment, 
        slot=EquipmentSlots.WEAPON.value,
        defaults={'item': None}
    )
    
    # Unequip current weapon if any
    old_weapon = None
    if weapon_slot.item:
        old_weapon = weapon_slot.item
    
    # Equip new weapon
    weapon_slot.item = weapon
    weapon_slot.save()
    
    result = f"Equipped {weapon.name}! Attack power increased by {weapon.attack_bonus}!"
    if old_weapon:
        result += f" (Unequipped {old_weapon.name})"
    
    return result


def equip_armor(hero, armor):
    """Handle armor-specific equipping logic"""
    # Check class restrictions
    if armor.hero_class_restriction and armor.hero_class_restriction != hero.hero_class:
        return f"Only {armor.hero_class_restriction.name}s can wear this armor!"

    # Get or create equipment for hero
    equipment, created = Equipment.objects.get_or_create(hero=hero)
    if created:
        # Create equipment slots if equipment was just created
        for slot_choice in EquipmentSlots:
            EquipmentSlot.objects.create(equipment=equipment, slot=slot_choice.value, item=None)

    # Get the armor slot
    armor_slot, created = EquipmentSlot.objects.get_or_create(
        equipment=equipment, 
        slot=EquipmentSlots.ARMOR.value,
        defaults={'item': None}
    )
    
    # Unequip current armor if any
    old_armor = None
    if armor_slot.item:
        old_armor = armor_slot.item
    
    # Equip new armor
    armor_slot.item = armor
    armor_slot.save()
    
    result = f"Equipped {armor.name}! Defense increased by {armor.defense_bonus}!"
    if old_armor:
        result += f" (Unequipped {old_armor.name})"
    
    return result


def equip_accessory(hero, accessory):
    """Handle accessory-specific equipping logic"""
    # Check class restrictions if any
    if hasattr(accessory, 'hero_class_restriction') and accessory.hero_class_restriction and accessory.hero_class_restriction != hero.hero_class:
        return f"Only {accessory.hero_class_restriction.name}s can use this accessory!"

    # Get or create equipment for hero
    equipment, created = Equipment.objects.get_or_create(hero=hero)
    if created:
        # Create equipment slots if equipment was just created
        for slot_choice in EquipmentSlots:
            EquipmentSlot.objects.create(equipment=equipment, slot=slot_choice.value, item=None)

    # Get the accessory slot
    accessory_slot, created = EquipmentSlot.objects.get_or_create(
        equipment=equipment, 
        slot=EquipmentSlots.ACCESSORY.value,
        defaults={'item': None}
    )
    
    # Unequip current accessory if any
    old_accessory = None
    if accessory_slot.item:
        old_accessory = accessory_slot.item
    
    # Equip new accessory
    accessory_slot.item = accessory
    accessory_slot.save()
    
    result = f"Equipped {accessory.name}!"
    if hasattr(accessory, 'critical_bonus') and accessory.critical_bonus > 0:
        result += f" Critical chance increased by {accessory.critical_bonus}%!"
    elif hasattr(accessory, 'block') and accessory.block > 0:
        result += f" Defense increased by {accessory.block}!"
    
    if old_accessory:
        result += f" (Unequipped {old_accessory.name})"
    
    return result


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
        if inventory is None:
            inventory_items = []
        else:
            inventory_items = inventory.all()  # Assuming Inventory has a method to get all items
        
        # Get equipped items
        try:
            equipment = hero.equipment
            equipped_slots = equipment.slots.all()
            for slot in equipped_slots:
                if slot.item:
                    equipped_items[slot.slot] = slot.item
        except Equipment.DoesNotExist:
            # Create equipment for hero if it doesn't exist
            equipment = Equipment.objects.create(hero=hero)
            # Create equipment slots
            for slot_choice in EquipmentSlots:
                EquipmentSlot.objects.create(equipment=equipment, slot=slot_choice.value, item=None)

    # Categorize items automatically using polymorphic types
    weapons = []
    offhands = []
    armor = []
    accessories = []
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
        elif isinstance(item, Accessory):
            accessories.append(item)
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
        'accessories': accessories,
        'consumables': consumables,
        'offhands': offhands,
        'other_items': other_items,
        'total_items': item_count,
        'total_value': items_value,
        'equipped_items': equipped_items,
        'equipment_slots': [slot for slot in EquipmentSlots],
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
        equipment = hero.equipment
        equipment_slot = equipment.slots.get(slot=slot_type)
        
        if equipment_slot.item:
            item_name = equipment_slot.item.name
            equipment_slot.item = None
            equipment_slot.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Unequipped {item_name} from {slot_type} slot',
                'slot_type': slot_type,
            })
        else:
            return JsonResponse({'error': f'No item equipped in {slot_type} slot'}, status=400)
            
    except Equipment.DoesNotExist:
        return JsonResponse({'error': 'No equipment found for hero'}, status=400)
    except EquipmentSlot.DoesNotExist:
        return JsonResponse({'error': f'Invalid slot type: {slot_type}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
