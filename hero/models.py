from django.db import models


class Hero(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, null=False)
    level = models.IntegerField(default=1)
    experience = models.IntegerField(default=0)
    hero_class = models.ForeignKey(
        'HeroClass', on_delete=models.CASCADE, null=False)
    # stats
    strength = models.IntegerField(default=10)
    constitution = models.IntegerField(default=10)
    agility = models.IntegerField(default=10)
    intelligence = models.IntegerField(default=10)

    max_health = models.IntegerField(default=100)
    current_health = models.IntegerField(default=100)
    max_mana = models.IntegerField(default=50)
    current_mana = models.IntegerField(default=50)

    is_in_combat = models.BooleanField(default=False)

    inventory = models.ForeignKey(
        'item.Inventory', on_delete=models.CASCADE, null=True, blank=True)

    def calculate_max_health(self):
        """Calculate max health based on constitution, level, and class"""
        base_health = self.hero_class.base_health if self.hero_class else 100
        constitution_bonus = (self.constitution - 10) * \
            2  # +2 HP per point above 10
        level_bonus = (self.level - 1) * 5  # +5 HP per level
        return base_health + constitution_bonus + level_bonus

    def update_health(self):
        """Update health values based on current stats"""
        self.max_health = self.calculate_max_health()
        self.current_health = self.max_health

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
        """Calculate health regeneration rate based on constitution per second"""
        if self.constitution <= 10:
            return 5  # Base regen rate
        else:
            # +1 HP regen per 2 points above 10
            return 5 + (self.constitution - 10) // 2

    @property
    def mana_regeneration_rate(self):
        """Calculate mana regeneration rate based on intelligence per second"""
        if self.intelligence <= 10:
            return 5  # Base regen rate
        else:
            # +1 MP regen per 2 points above 10
            return 5 + (self.intelligence - 10) // 2

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
        self.current_health = min(
            self.max_health, self.current_health + amount)
        self.save()

    def add_to_inventory(self, item, quantity=1):
        """Add item to hero's inventory"""
        inventory_item, created = InventoryItem.objects.get_or_create(
            inventory=self.inventory, item=item, quantity=quantity)
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
    base_health = models.IntegerField(default=100)
    base_strength = models.IntegerField(default=10)
    base_constitution = models.IntegerField(default=10)
    base_agility = models.IntegerField(default=10)
    base_intelligence = models.IntegerField(default=10)

    def __str__(self):
        return self.name
