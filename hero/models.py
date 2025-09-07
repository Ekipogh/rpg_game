from django.db import models

# Create your models here.
class Hero(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, null=False)
    level = models.IntegerField(default=1)
    experience = models.IntegerField(default=0)
    hero_class = models.ForeignKey('HeroClass', on_delete=models.CASCADE, null=False)
    health = models.IntegerField(default=100)
    # stats
    strength = models.IntegerField(default=10)
    constitution = models.IntegerField(default=10)
    agility = models.IntegerField(default=10)
    intelligence = models.IntegerField(default=10)

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
