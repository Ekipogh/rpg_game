import enum
from django.db import models

class EquipmentSlots(enum.Enum):
    HEAD = "head"
    CHEST = "chest"
    LEGS = "legs"
    FEET = "feet"
    HANDS = "hands"
    WEAPON = "weapon"
    SHIELD = "shield"

    @classmethod
    def choices(cls):
        return [(slot.value, slot.name.capitalize()) for slot in cls]

# Create your models here.
class Item(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, null=False)
    description = models.TextField(blank=True)
    value = models.IntegerField(default=0)
    hero_class_restriction = models.ForeignKey('hero.HeroClass', on_delete=models.CASCADE, null=True, blank=True)

class Weapon(Item):
    damage = models.IntegerField(default=10)
    weapon_type = models.CharField(max_length=50, default='sword')
    equipment_slot = models.CharField(max_length=50, choices=EquipmentSlots.choices(), default=EquipmentSlots.WEAPON.value)

class OfHand(Item):
    block = models.IntegerField(default=5)
    shield_type = models.CharField(max_length=50, default='wooden')
    equipment_slot = models.CharField(max_length=50, choices=EquipmentSlots.choices(), default=EquipmentSlots.SHIELD.value)

class Armor(Item):
    defense = models.IntegerField(default=5)
    armor_type = models.CharField(max_length=50, default='leather')
    equipment_slot = models.CharField(max_length=50, choices=EquipmentSlots.choices(), default=EquipmentSlots.HEAD.value)

class Consumable(Item):
    heal_amount = models.IntegerField(default=20)
    mana_restore = models.IntegerField(default=0)
    duration = models.IntegerField(default=0)  # Duration in seconds for buffs/debuffs

    def use(self, hero):
        """Apply the consumable effect to the hero"""
        if self.heal_amount > 0:
            hero.current_health = min(hero.current_health + self.heal_amount, hero.max_health)
            hero.save()
        if self.mana_restore > 0:
            # Assuming hero has a mana attribute
            hero.current_mana = min(hero.current_mana + self.mana_restore, hero.max_mana)
            hero.save()
