from django.core.exceptions import ValidationError
from django_unicorn.components import UnicornView
from hero.models import Hero, HeroClass


class CharacterFormView(UnicornView):
    name: str = ""
    selected_class: str = ""
    points_available: int = 10
    strength: int = 10
    constitution: int = 10
    agility: int = 10
    intelligence: int = 10

    def select_class(self, cls: str):
        self.selected_class = cls

    def increase_stat(self, stat: str):
        if self.points_available > 0:
            self.points_available -= 1
            setattr(self, stat, getattr(self, stat) + 1)

    def decrease_stat(self, stat: str):
        if self.points_available < 10:
            self.points_available += 1
        current = getattr(self, stat)
        if current > 1:  # prevent going below 1
            setattr(self, stat, current - 1)

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
        hero.save()

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
