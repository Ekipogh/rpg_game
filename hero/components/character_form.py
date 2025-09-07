from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django_unicorn.components import UnicornView
from hero.models import Hero, HeroClass


class CharacterFormView(UnicornView):
    name: str = ""
    hero_class = HeroClass.objects.first()
    selected_class: str = hero_class.name if hero_class else ""
    if hero_class:
        strength: int = hero_class.base_strength
        constitution: int = hero_class.base_constitution
        agility: int = hero_class.base_agility
        intelligence: int = hero_class.base_intelligence
    else:
        strength: int = 10
        constitution: int = 10
        agility: int = 10
        intelligence: int = 10
    strength_mod: int = 0
    constitution_mod: int = 0
    agility_mod: int = 0
    intelligence_mod: int = 0

    strength_total: int = strength + strength_mod
    constitution_total: int = constitution + constitution_mod
    agility_total: int = agility + agility_mod
    intelligence_total: int = intelligence + intelligence_mod

    points_available: int = 10

    def select_class(self, cls: str):
        hero_class = HeroClass.objects.filter(name=cls).first()
        if hero_class:
            self.strength = hero_class.base_strength
            self.constitution = hero_class.base_constitution
            self.agility = hero_class.base_agility
            self.intelligence = hero_class.base_intelligence
        self.update_totals()
        self.selected_class = cls

    def increase_stat(self, stat: str):
        stat_name = stat + "_mod"
        if self.points_available > 0:
            self.points_available -= 1
            setattr(self, stat_name, getattr(self, stat_name) + 1)
            self.update_totals()

    def decrease_stat(self, stat: str):
        stat_name = stat + "_mod"
        if self.points_available < 10:
            self.points_available += 1
        current = getattr(self, stat_name)
        if current > 1:  # prevent going below 1
            setattr(self, stat_name, current - 1)
        self.update_totals()

    def update_totals(self):
        self.strength_total = self.strength + self.strength_mod
        self.constitution_total = self.constitution + self.constitution_mod
        self.agility_total = self.agility + self.agility_mod
        self.intelligence_total = self.intelligence + self.intelligence_mod

    def submit(self):
        # For now just print, later you can save to DB
        self.validate_form()
        if not self.is_valid():
            return
        print(f"Creating character: {self.name}, Class: {self.selected_class}")
        hero_class = HeroClass.objects.get(name=self.selected_class)
        hero = Hero.objects.create(
            name=self.name,
            hero_class=hero_class,
            strength=self.strength,
            constitution=self.constitution,
            agility=self.agility,
            intelligence=self.intelligence,
        )
        hero.update_health()
        hero.save()
        return redirect('select_hero', hero_id=hero.id)


    def validate_form(self):
        errors = {}
        if not self.name:
            errors["name"] = "Name is required."
        elif Hero.objects.filter(name=self.name).exists():
            errors["name"] = "Name already taken."

        if not self.selected_class:
            errors["selected_class"] = "You must select a class."

        if self.points_available != 0:
            errors["points_available"] = "You must allocate all available points."

        if errors:
            raise ValidationError(errors, code="invalid")
