from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator

from item.models import EquipmentSlots, Inventory, InventoryItem


class Hero(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, null=False)
    level = models.IntegerField(default=1)
    experience = models.IntegerField(default=0)
    hero_class = models.ForeignKey("HeroClass", on_delete=models.CASCADE, null=False)

    # Primary Stats (BATTLE_SYSTEM.md)
    max_health = models.IntegerField(default=100)  # HP
    current_health = models.IntegerField(default=100)
    max_mana = models.IntegerField(default=50)  # MP
    current_mana = models.IntegerField(default=50)
    attack = models.IntegerField(default=10)  # ATK
    defense = models.IntegerField(default=10)  # DEF
    magic = models.IntegerField(default=10)  # MAG
    magic_defense = models.IntegerField(default=10)  # MDEF
    speed = models.IntegerField(default=10)  # SPD

    # Secondary Stats (BATTLE_SYSTEM.md)
    accuracy = models.IntegerField(default=100)  # ACC
    evasion = models.IntegerField(default=0)  # EVA
    critical_chance = models.IntegerField(default=5)  # CRIT (percentage)
    critical_damage = models.FloatField(default=1.5)  # CRITDMG (multiplier)

    is_in_combat = models.BooleanField(default=False)

    dungeon_run = models.JSONField(default=dict, blank=True)
    dungeon_revision = models.IntegerField(default=0)

    money = models.IntegerField(default=0)

    inventory = models.ForeignKey(
        "item.Inventory", on_delete=models.CASCADE, null=True, blank=True
    )

    def level_up(self):
        """Increase stats based on hero class bonuses"""
        import random

        if not self.hero_class:
            return

        self.level += 1

        # Increase stats based on class bonuses (min-max ranges)
        self.attack += random.randint(
            self.hero_class.atk_gain_min, self.hero_class.atk_gain_max
        )
        self.defense += random.randint(
            self.hero_class.def_gain_min, self.hero_class.def_gain_max
        )
        self.magic += random.randint(
            self.hero_class.mag_gain_min, self.hero_class.mag_gain_max
        )
        self.magic_defense += random.randint(
            self.hero_class.mdef_gain_min, self.hero_class.mdef_gain_max
        )
        self.speed += random.randint(
            self.hero_class.spd_gain_min, self.hero_class.spd_gain_max
        )

        # Increase HP and MP
        hp_gain = random.randint(
            self.hero_class.hp_gain_min, self.hero_class.hp_gain_max
        )
        mp_gain = random.randint(
            self.hero_class.mp_gain_min, self.hero_class.mp_gain_max
        )

        self.max_health += hp_gain
        self.max_mana += mp_gain

        # Fully restore HP and MP on level up
        self.current_health = self.max_health
        self.current_mana = self.max_mana

        self.save()

    @property
    def next_level_xp(self):
        """Calculate XP needed for next level"""
        return 100 * self.level  # Simple formula: 100 XP per level

    @property
    def experience_percentage(self):
        """Calculate experience percentage for progress bar"""
        if self.next_level_xp == 0:
            return 0
        return min((self.experience / self.next_level_xp) * 100, 100)

    @property
    def health_percentage(self):
        """Calculate health percentage for progress bar"""
        if self.max_health == 0:
            return 0
        return (self.current_health / self.max_health) * 100

    @property
    def mana_percentage(self):
        """Calculate mana percentage for progress bar"""
        if self.max_mana == 0:
            return 0
        return (self.current_mana / self.max_mana) * 100

    @property
    def health_regeneration_rate(self):
        """Calculate health regeneration rate per second"""
        # Base regen rate: 1% of max HP per second
        return max(1, self.max_health // 100)

    @property
    def mana_regeneration_rate(self):
        """Calculate mana regeneration rate per second"""
        # Base regen rate: 1% of max MP per second
        return max(1, self.max_mana // 100)

    @property
    def attack_mod(self):
        """Calculate attack modifier from equipment and buffs"""
        mod = 0
        if self.weapon:
            mod += getattr(self.weapon, "attack_bonus", 0)
        return mod

    @property
    def defense_mod(self):
        """Calculate defense modifier from equipment and buffs"""
        mod = 0
        if self.armor:
            mod += getattr(self.armor, "defense_bonus", 0)
        if self.accessory:
            mod += getattr(self.accessory, "defense_bonus", 0)
        return mod

    @property
    def magic_mod(self):
        """Calculate magic modifier from equipment and buffs"""
        mod = 0
        if self.accessory:
            mod += getattr(self.accessory, "magic_bonus", 0)
        return mod

    @property
    def speed_mod(self):
        """Calculate speed modifier from equipment and buffs"""
        mod = 0
        if self.accessory:
            mod += getattr(self.accessory, "speed_bonus", 0)
        return mod

    @property
    def magic_defense_mod(self):
        """Calculate magic defense modifier from equipment and buffs"""
        mod = 0
        if self.armor:
            mod += getattr(self.armor, "magic_defense_bonus", 0)
        if self.accessory:
            mod += getattr(self.accessory, "magic_defense_bonus", 0)
        return mod

    @property
    def weapon(self):
        """Get equipped weapon item"""
        try:
            from item.models import Equipment, EquipmentSlot

            equipment_slot = EquipmentSlot.objects.filter(
                equipment__hero=self, slot=EquipmentSlots.WEAPON.value
            ).first()
            return equipment_slot.item if equipment_slot else None
        except Exception:
            return None

    @property
    def armor(self):
        """Get equipped armor item"""
        try:
            from item.models import Equipment, EquipmentSlot

            equipment_slot = EquipmentSlot.objects.filter(
                equipment__hero=self, slot=EquipmentSlots.ARMOR.value
            ).first()
            return equipment_slot.item if equipment_slot else None
        except Exception:
            return None

    @property
    def accessory(self):
        """Get equipped accessory item"""
        try:
            from item.models import Equipment, EquipmentSlot

            equipment_slot = EquipmentSlot.objects.filter(
                equipment__hero=self, slot=EquipmentSlots.ACCESSORY.value
            ).first()
            return equipment_slot.item if equipment_slot else None
        except Exception:
            return None

    def take_damage(self, damage):
        """
        Deal damage to hero and start healing if not at full health
        """
        self.current_health = max(0, self.current_health - damage)
        self.save()

        # Start healing if hero is not at full health
        if self.current_health < self.max_health and self.current_health > 0:
            # Import here to avoid circular imports
            from .windows_tasks import start_hero_healing

            start_hero_healing(self.id)

    def heal(self, amount):
        """
        Heal hero by specified amount
        """
        self.current_health = min(self.max_health, self.current_health + amount)
        self.save()

    def add_to_inventory(self, item, quantity=1):
        """Receive items; Instant effects apply immediately instead of being stored."""
        from item.services import receive_item
        return receive_item(self, item, quantity)

    def remove_item(self, item, quantity=1):
        """Remove item from hero's inventory"""
        if not self.inventory:
            return
        inventory_item, created = InventoryItem.objects.get_or_create(
            inventory=self.inventory, item=item, defaults={"quantity": 0}
        )
        inventory_item.quantity = max(0, inventory_item.quantity - quantity)
        inventory_item.save(update_fields=["quantity"])
        if inventory_item.quantity == 0:
            inventory_item.delete()

    def store_dungeon_run(self, dungeon_data):
        """Store the current dungeon run data in the hero's record"""
        if not self.validate_dungeon_data(dungeon_data):
            raise ValueError("Invalid dungeon data format.")
        self.dungeon_run = dungeon_data
        self.dungeon_revision += 1
        self.save(update_fields=["dungeon_run", "dungeon_revision"])

    def validate_dungeon_data(self, dungeon_data):
        """Validate the structure of the dungeon data"""
        required_keys = {
            "current_floor",
            "current_encounter",
            "phase",
            "last_result",
            "path_left",
            "path_right",
        }
        if not isinstance(dungeon_data, dict):
            return False
        if not required_keys.issubset(dungeon_data.keys()):
            return False
        return True

    def __str__(self):
        return self.name

    @property
    def not_healed(self):
        """Check if the hero is at less than 80% of max health"""
        return self.max_health <= 0 or self.current_health * 5 < self.max_health * 4


class HeroClass(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    description = models.TextField()
    image = models.ImageField(upload_to="hero_classes/", blank=True)

    # Base stats at level 1
    base_health = models.IntegerField(default=100)  # HP
    base_mana = models.IntegerField(default=50)  # MP
    base_attack = models.IntegerField(default=10)  # ATK
    base_defense = models.IntegerField(default=10)  # DEF
    base_magic = models.IntegerField(default=10)  # MAG
    base_magic_defense = models.IntegerField(default=10)  # MDEF
    base_speed = models.IntegerField(default=10)  # SPD

    # Stat growth per level (min-max ranges)
    # Example: Warrior gets 2-3 ATK, 1-2 DEF, 0-1 MAG, 0-1 MDEF, 1-2 SPD, 5-10 HP, 0-5 MP
    atk_gain_min = models.IntegerField(default=1)
    atk_gain_max = models.IntegerField(default=2)
    def_gain_min = models.IntegerField(default=1)
    def_gain_max = models.IntegerField(default=2)
    mag_gain_min = models.IntegerField(default=0)
    mag_gain_max = models.IntegerField(default=1)
    mdef_gain_min = models.IntegerField(default=0)
    mdef_gain_max = models.IntegerField(default=1)
    spd_gain_min = models.IntegerField(default=1)
    spd_gain_max = models.IntegerField(default=2)
    hp_gain_min = models.IntegerField(default=5)
    hp_gain_max = models.IntegerField(default=10)
    mp_gain_min = models.IntegerField(default=2)
    mp_gain_max = models.IntegerField(default=5)

    def __str__(self):
        return self.name


class HeroClassEquipment(models.Model):
    """Imported starting loadout, shared by new heroes of a class."""

    hero_class = models.ForeignKey(HeroClass, on_delete=models.CASCADE, related_name="initial_equipment")
    slot = models.CharField(max_length=50, choices=EquipmentSlots.choices())
    item = models.ForeignKey("item.Item", on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hero_class", "slot"], name="hero_class_initial_slot_unique"),
        ]

    def clean(self):
        super().clean()
        if self.item_id:
            from item.models import Weapon, Armor, Accessory
            expected = {"weapon": Weapon, "armor": Armor, "accessory": Accessory}.get(self.slot)
            if expected is None or not isinstance(self.item, expected) or self.item.equipment_slot != self.slot:
                raise ValidationError("Initial equipment must match its slot.")
            if self.item.level_requirement > 1:
                raise ValidationError("Initial equipment must be usable at level 1.")
            if self.item.hero_class_restriction_id not in (None, self.hero_class_id):
                raise ValidationError("Initial equipment is restricted to another class.")


class Monster(models.Model):
    attack_range_max = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(8)]
    )

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, null=False)
    level = models.IntegerField(default=1)
    max_health = models.IntegerField(default=100)
    current_health = models.IntegerField(default=100)
    max_mana = models.IntegerField(default=50)
    current_mana = models.IntegerField(default=50)
    attack = models.IntegerField(default=10)
    defense = models.IntegerField(default=10)
    magic = models.IntegerField(default=10)
    magic_defense = models.IntegerField(default=10)
    speed = models.IntegerField(default=10)
    accuracy = models.IntegerField(default=100)
    evasion = models.IntegerField(default=0)
    critical_chance = models.IntegerField(default=5)
    critical_damage = models.FloatField(default=1.5)
    THREAT_LEVEL_CHOICES = [
        ("common", "Common"),
        ("miniboss", "Miniboss"),
        ("boss", "Boss"),
    ]
    threat_level = models.CharField(
        max_length=10, choices=THREAT_LEVEL_CHOICES, default="common"
    )
    experience_reward = models.PositiveIntegerField(default=0)
    MONSTER_CLASS_CHOICES = [
        ("warrior", "Warrior"),
        ("mage", "Mage"),
        ("archer", "Archer"),
        ("rogue", "Rogue"),
        ("tank", "Tank"),
        ("healer", "Healer"),
    ]
    monster_class = models.CharField(
        max_length=10, choices=MONSTER_CLASS_CHOICES, default="warrior"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(threat_level__in=["common", "miniboss", "boss"]),
                name="valid_threat_level",
            ),
            models.CheckConstraint(
                condition=models.Q(experience_reward__gte=0),
                name="monster_experience_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(attack_range_max__gte=1, attack_range_max__lte=8),
                name="monster_valid_attack_range",
            ),
        ]

    def __str__(self):
        return self.name


class MonsterLoot(models.Model):
    id = models.AutoField(primary_key=True)
    monster = models.ForeignKey(Monster, on_delete=models.CASCADE, related_name="loot")
    item = models.ForeignKey("item.Item", on_delete=models.CASCADE)
    drop_chance = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    min_quantity = models.PositiveIntegerField(default=1)
    max_quantity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(drop_chance__gte=0) & models.Q(drop_chance__lte=100),
                name="monster_loot_drop_chance_range",
            ),
            models.CheckConstraint(
                condition=models.Q(min_quantity__gte=1),
                name="monster_loot_min_quantity_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(max_quantity__gte=1),
                name="monster_loot_max_quantity_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(min_quantity__lte=models.F("max_quantity")),
                name="monster_loot_quantity_range",
            ),
        ]

    def __str__(self):
        return f"{self.item.name} from {self.monster.name}"

    def clean(self):
        """Ensure drop chance is between 0 and 100 and min_quantity <= max_quantity."""
        super().clean()
        if not (0 <= self.drop_chance <= 100):
            raise ValidationError("Drop chance must be between 0 and 100.")
        if self.min_quantity < 1 or self.max_quantity < 1:
            raise ValidationError("Loot quantities must be positive.")
        if self.min_quantity > self.max_quantity:
            raise ValidationError("min_quantity cannot be greater than max_quantity.")
