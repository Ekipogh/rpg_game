from django.db import models

from item.models import InventoryItem


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
        self.attack += random.randint(self.hero_class.atk_gain_min, self.hero_class.atk_gain_max)
        self.defense += random.randint(self.hero_class.def_gain_min, self.hero_class.def_gain_max)
        self.magic += random.randint(self.hero_class.mag_gain_min, self.hero_class.mag_gain_max)
        self.magic_defense += random.randint(self.hero_class.mdef_gain_min, self.hero_class.mdef_gain_max)
        self.speed += random.randint(self.hero_class.spd_gain_min, self.hero_class.spd_gain_max)

        # Increase HP and MP
        hp_gain = random.randint(self.hero_class.hp_gain_min, self.hero_class.hp_gain_max)
        mp_gain = random.randint(self.hero_class.mp_gain_min, self.hero_class.mp_gain_max)

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
        """Add item to hero's inventory"""
        inventory_item, created = InventoryItem.objects.get_or_create(
            inventory=self.inventory, item=item, quantity=quantity
        )
        if not created:
            inventory_item.quantity += quantity
        else:
            inventory_item.quantity = quantity
        inventory_item.save()

    def __str__(self):
        return self.name


class HeroClass(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    description = models.TextField()

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
