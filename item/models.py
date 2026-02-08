import enum
from django.db import models
from polymorphic.models import PolymorphicModel


class EquipmentSlots(enum.Enum):
    """Equipment slots according to BATTLE_SYSTEM.md"""
    WEAPON = "weapon"
    ARMOR = "armor"
    ACCESSORY = "accessory"

    @classmethod
    def choices(cls):
        return [(slot.value, slot.name.capitalize()) for slot in cls]


class ItemTypes(enum.Enum):
    GENERIC = "generic"
    WEAPON = "weapon"
    ARMOR = "armor"
    ACCESSORY = "accessory"
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
    level_requirement = models.IntegerField(default=1)

    @property
    def item_type(self):
        return ItemTypes.GENERIC.value

    def __str__(self):
        return self.name


class Weapon(Item):
    """Weapon equipment (BATTLE_SYSTEM.md: +ATK, +ACC, Optional element)"""
    attack_bonus = models.IntegerField(default=0)  # +ATK
    accuracy_bonus = models.IntegerField(default=0)  # +ACC
    element = models.CharField(max_length=50, blank=True, null=True,
        choices=[
            ('fire', 'Fire'),
            ('ice', 'Ice'),
            ('lightning', 'Lightning'),
            ('earth', 'Earth'),
            ('wind', 'Wind'),
            ('holy', 'Holy'),
            ('dark', 'Dark'),
        ])  # Optional element
    weapon_type = models.CharField(max_length=50, default='sword')
    equipment_slot = models.CharField(
        max_length=50, choices=EquipmentSlots.choices(), default=EquipmentSlots.WEAPON.value)

    @property
    def item_type(self):
        return ItemTypes.WEAPON.value

    def get_stats(self):
        stats = f"ATK +{self.attack_bonus}, ACC +{self.accuracy_bonus}"
        if self.element:
            stats += f", Element: {self.element.capitalize()}"
        return stats


class Armor(Item):
    """Armor equipment (BATTLE_SYSTEM.md: +DEF, +HP, Elemental resistances)"""
    defense_bonus = models.IntegerField(default=5)  # +DEF
    magic_defense_bonus = models.IntegerField(default=0)  # +MDEF
    health_bonus = models.IntegerField(default=0)  # +HP
    armor_type = models.CharField(max_length=50, default='leather')
    # Elemental resistances stored as JSON: {"fire": 0.75, "ice": 0.5}
    elemental_resistances = models.JSONField(default=dict, blank=True)
    equipment_slot = models.CharField(
        max_length=50, choices=EquipmentSlots.choices(), default=EquipmentSlots.ARMOR.value)

    @property
    def item_type(self):
        return ItemTypes.ARMOR.value

    def get_stats(self):
        stats = f"DEF +{self.defense_bonus}"
        if self.health_bonus > 0:
            stats += f", HP +{self.health_bonus}"
        if self.elemental_resistances:
            resists = [f"{elem.capitalize()}: {int((1-val)*100)}%" for elem, val in self.elemental_resistances.items()]
            stats += f", Resistances: {', '.join(resists)}"
        return stats


class Accessory(Item):
    """Accessory equipment (BATTLE_SYSTEM.md: +CRIT, Status immunities, Passive effects)"""
    defense_bonus = models.IntegerField(default=0)  # +DEF
    speed_bonus = models.IntegerField(default=0)  # +SPD
    magic_bonus = models.IntegerField(default=0)  # +MAG
    magic_defense_bonus = models.IntegerField(default=0)  # +MDEF
    critical_bonus = models.IntegerField(default=0)  # +CRIT (percentage)
    # Status immunities stored as JSON list: ["poison", "burn"]
    status_immunities = models.JSONField(default=list, blank=True)
    # Passive effects stored as JSON: {"atk_percent": 10, "def_flat": 5}
    passive_effects = models.JSONField(default=dict, blank=True)
    accessory_type = models.CharField(max_length=50, default='ring')
    equipment_slot = models.CharField(
        max_length=50, choices=EquipmentSlots.choices(), default=EquipmentSlots.ACCESSORY.value)

    @property
    def item_type(self):
        return ItemTypes.ACCESSORY.value

    def get_stats(self):
        stats = []
        if self.critical_bonus > 0:
            stats.append(f"CRIT +{self.critical_bonus}%")
        if self.status_immunities:
            stats.append(f"Immune: {', '.join([s.capitalize() for s in self.status_immunities])}")
        if self.passive_effects:
            for effect, value in self.passive_effects.items():
                stats.append(f"{effect.replace('_', ' ').title()}: +{value}")
        return ", ".join(stats) if stats else "No special effects"


class Consumable(Item):
    """Consumable items (potions, elixirs, etc.)"""
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
