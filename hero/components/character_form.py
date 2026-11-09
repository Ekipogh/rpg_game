from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django_unicorn.components import UnicornView
from hero.models import Hero, HeroClass
from hero.creation import create_character


class CharacterFormView(UnicornView):
    class Meta:
        # Render database choices on the server without hydrating this read-only property.
        javascript_exclude = ("hero_classes",)

    name: str = ""
    selected_class: int = 0
    attack: int = 0
    defense: int = 0
    magic: int = 0
    magic_defense: int = 0
    speed: int = 0
    attack_mod: int = 0
    defense_mod: int = 0
    magic_mod: int = 0
    magic_defense_mod: int = 0
    speed_mod: int = 0

    attack_total: int = attack + attack_mod
    defense_total: int = defense + defense_mod
    magic_total: int = magic + magic_mod
    magic_defense_total: int = magic_defense + magic_defense_mod
    speed_total: int = speed + speed_mod

    @property
    def hero_classes(self):
        classes = []
        for hero_class in HeroClass.objects.order_by("pk"):
            classes.append({
                "id": hero_class.pk,
                "name": hero_class.name,
                "description": hero_class.description,
                "image": hero_class.image.url if hero_class.image else "",
            })
        return classes

    def mount(self):
        hero_class = HeroClass.objects.order_by("pk").first()
        if hero_class:
            self.select_class(hero_class.pk)

    def select_class(self, class_id: int):
        hero_class = HeroClass.objects.filter(pk=class_id).first()
        if hero_class is None:
            return
        self.attack = hero_class.base_attack
        self.defense = hero_class.base_defense
        self.magic = hero_class.base_magic
        self.magic_defense = hero_class.base_magic_defense
        self.speed = hero_class.base_speed
        self.selected_class = hero_class.pk
        self.update_totals()

    def update_totals(self):
        self.attack_total = self.attack + self.attack_mod
        self.defense_total = self.defense + self.defense_mod
        self.magic_total = self.magic + self.magic_mod
        self.magic_defense_total = self.magic_defense + self.magic_defense_mod
        self.speed_total = self.speed + self.speed_mod

    def submit(self):
        self.validate_form()
        if not self.is_valid():
            return
        hero_class = HeroClass.objects.get(pk=self.selected_class)
        hero = create_character(self.name, hero_class)
        return redirect('select_hero', hero_id=hero.id)

    def validate_form(self):
        errors = {}
        if not self.name:
            errors["name"] = "Name is required."
        elif Hero.objects.filter(name=self.name).exists():
            errors["name"] = "Name already taken."

        if not HeroClass.objects.filter(pk=self.selected_class).exists():
            errors["selected_class"] = "You must select a class."

        if errors:
            raise ValidationError(errors, code="invalid")
