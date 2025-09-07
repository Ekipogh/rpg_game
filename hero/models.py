from django.db import models

# Create your models here.
class Hero(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, null=False)
    level = models.IntegerField(default=1)
    experience = models.IntegerField(default=0)
    hero_class = models.ForeignKey('HeroClass', on_delete=models.CASCADE, null=False)
    # stats
    strength = models.IntegerField(default=10)
    constitution = models.IntegerField(default=10)
    agility = models.IntegerField(default=10)
    intelligence = models.IntegerField(default=10)

    health = models.IntegerField(default=100)
    current_health = models.IntegerField(default=100)

    is_in_combat = models.BooleanField(default=False)

    def calculate_max_health(self):
        """Calculate max health based on constitution, level, and class"""
        base_health = self.hero_class.base_health if self.hero_class else 100
        constitution_bonus = (self.constitution - 10) * 2  # +2 HP per point above 10
        level_bonus = (self.level - 1) * 5  # +5 HP per level
        return base_health + constitution_bonus + level_bonus

    def update_health(self):
        """Update health values based on current stats"""
        self.health = self.calculate_max_health()
        self.current_health = self.health

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
        if self.health == 0:
            return 0
        return (self.current_health / self.health) * 100

    def take_damage(self, damage):
        """
        Deal damage to hero and start healing if not at full health
        """
        self.current_health = max(0, self.current_health - damage)
        self.save()

        # Start healing if hero is not at full health
        if self.current_health < self.health and self.current_health > 0:
            # Import here to avoid circular imports
            from .windows_tasks import start_hero_healing
            start_hero_healing(self.id)

    def heal(self, amount):
        """
        Heal hero by specified amount
        """
        self.current_health = min(self.health, self.current_health + amount)
        self.save()

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
