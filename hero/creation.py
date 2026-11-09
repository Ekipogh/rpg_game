"""Create a hero with its imported class loadout in one transaction."""
from django.db import transaction

from hero.models import Hero
from item.models import Equipment, EquipmentSlot, Inventory


@transaction.atomic
def create_character(name, hero_class):
    hero = Hero.objects.create(
        name=name, hero_class=hero_class, inventory=Inventory.objects.create(),
        max_health=hero_class.base_health, current_health=hero_class.base_health,
        max_mana=hero_class.base_mana, current_mana=hero_class.base_mana,
        attack=hero_class.base_attack, defense=hero_class.base_defense,
        magic=hero_class.base_magic, magic_defense=hero_class.base_magic_defense,
        speed=hero_class.base_speed,
    )
    equipment = Equipment.objects.create(hero=hero)
    for entry in hero_class.initial_equipment.prefetch_related('item'):
        entry.full_clean()
        EquipmentSlot.objects.create(equipment=equipment, slot=entry.slot, item=entry.item)
    return hero
