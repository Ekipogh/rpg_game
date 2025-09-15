import enum
from django.db import models
from polymorphic.models import PolymorphicModel


class EquipmentSlots(enum.Enum):
    HEAD = "head"
    ARMOR = "armor"
    MAIN_HAND = "main_hand"
    OFFHAND = "offhand"
    CONSUMABLE_1 = "consumable_1"
    CONSUMABLE_2 = "consumable_2"
    CONSUMABLE_3 = "consumable_3"
    LEGS = "legs"
    HANDS = "hands"

    @classmethod
    def choices(cls):
        return [(slot.value, slot.name.capitalize()) for slot in cls]


class ItemTypes(enum.Enum):
    GENERIC = "generic"
    WEAPON = "weapon"
    OFF_HAND = "off_hand"
    ARMOR = "armor"
    CONSUMABLE = "consumable"

    @classmethod
    def choices(cls):
        return [(item_type.value, item_type.name.capitalize()) for item_type in cls]


# Create your models here.
class Item(PolymorphicModel):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, null=False)
    description = models.TextField(blank=True)
    value = models.IntegerField(default=0)
    hero_class_restriction = models.ForeignKey(
        'hero.HeroClass', on_delete=models.CASCADE, null=True, blank=True)

    @property
    def item_type(self):
        return ItemTypes.GENERIC.value

    def __str__(self):
        return self.name


class Weapon(Item):
    damage = models.IntegerField(default=10)
    weapon_type = models.CharField(max_length=50, default='sword')
    equipment_slot = models.CharField(
        max_length=50, choices=EquipmentSlots.choices(), default=EquipmentSlots.MAIN_HAND.value)

    @property
    def item_type(self):
        return ItemTypes.WEAPON.value

    def get_stats(self):
        return f"Damage: {self.damage}, Type: {self.weapon_type}"


class OffHand(Item):
    block = models.IntegerField(default=5)
    shield_type = models.CharField(max_length=50, default='wooden')
    equipment_slot = models.CharField(
        max_length=50, choices=EquipmentSlots.choices(), default=EquipmentSlots.OFFHAND.value)

    @property
    def item_type(self):
        return ItemTypes.OFF_HAND.value

    def get_stats(self):
        return f"Block: {self.block}, Type: {self.shield_type}"


class Armor(Item):
    defense = models.IntegerField(default=5)
    armor_type = models.CharField(max_length=50, default='leather')
    equipment_slot = models.CharField(
        max_length=50, choices=EquipmentSlots.choices(), default=EquipmentSlots.HEAD.value)

    @property
    def item_type(self):
        return ItemTypes.ARMOR.value

    def get_stats(self):
        return f"Defense: {self.defense}, Type: {self.armor_type}"


class Consumable(Item):
    heal_amount = models.IntegerField(default=20)
    mana_restore = models.IntegerField(default=0)
    # Duration in seconds for buffs/debuffs
    duration = models.IntegerField(default=0)

    @property
    def item_type(self):
        return ItemTypes.CONSUMABLE.value

    def get_stats(self):
        stats = []
        if self.heal_amount > 0:
            stats.append(f"Heals: {self.heal_amount}")
        if self.mana_restore > 0:
            stats.append(f"Mana: {self.mana_restore}")
        if self.duration > 0:
            stats.append(f"Duration: {self.duration}s")
        return ", ".join(stats) if stats else "No special effects"

    def use(self, hero):
        """Apply the consumable effect to the hero"""
        if self.heal_amount > 0:
            hero.current_health = min(
                hero.current_health + self.heal_amount, hero.max_health)
            hero.save()
        if self.mana_restore > 0:
            # Assuming hero has a mana attribute
            hero.current_mana = min(
                hero.current_mana + self.mana_restore, hero.max_mana)
            hero.save()

class Inventory(models.Model):
    id = models.AutoField(primary_key=True)
    updated_at = models.DateTimeField(auto_now=True)

    def all(self):
        return InventoryItem.objects.filter(inventory=self)

class InventoryItem(models.Model):
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)

    class Meta:
        unique_together = ('inventory', 'item')

class Equipment(models.Model):
    id = models.AutoField(primary_key=True)
    # One-to-one: each Hero has exactly one Equipment set; access via hero.equipment
    hero = models.OneToOneField('hero.Hero', on_delete=models.CASCADE, related_name='equipment')
    updated_at = models.DateTimeField(auto_now=True)

class EquipmentSlot(models.Model):
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='slots')
    slot = models.CharField(max_length=50, choices=EquipmentSlots.choices())
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ('equipment', 'slot')

    SLOT_CHOICES = EquipmentSlots.choices()
