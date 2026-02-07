from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django_unicorn.components import UnicornView
from hero.models import Hero, HeroClass
from item.models import Inventory, Item, EquipmentSlots, Weapon, Armor, OffHand, Consumable


class CharacterFormView(UnicornView):
    name: str = ""
    hero_class = HeroClass.objects.first()
    selected_class: str = hero_class.name if hero_class else ""
    if hero_class:
        attack: int = hero_class.base_attack
        defense: int = hero_class.base_defense
        magic: int = hero_class.base_magic
        magic_defense: int = hero_class.base_magic_defense
        speed: int = hero_class.base_speed
    else:
        attack: int = 10
        defense: int = 10
        magic: int = 10
        magic_defense: int = 10
        speed: int = 10
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

    def select_class(self, cls: str):
        hero_class = HeroClass.objects.filter(name=cls).first()
        if hero_class:
            self.attack = hero_class.base_attack
            self.defense = hero_class.base_defense
            self.magic = hero_class.base_magic
            self.magic_defense = hero_class.base_magic_defense
            self.speed = hero_class.base_speed
        self.update_totals()
        self.selected_class = cls

    def update_totals(self):
        self.attack_total = self.attack + self.attack_mod
        self.defense_total = self.defense + self.defense_mod
        self.magic_total = self.magic + self.magic_mod
        self.magic_defense_total = self.magic_defense + self.magic_defense_mod
        self.speed_total = self.speed + self.speed_mod

    def submit(self):
        # For now just print, later you can save to DB
        self.validate_form()
        if not self.is_valid():
            return
        print(f"Creating character: {self.name}, Class: {self.selected_class}")
        hero_class = HeroClass.objects.get(name=self.selected_class)
        inventory = Inventory.objects.create()
        hero = Hero.objects.create(
            name=self.name,
            hero_class=hero_class,
            attack=self.attack_total,
            defense=self.defense_total,
            magic=self.magic_total,
            magic_defense=self.magic_defense_total,
            speed=self.speed_total,
            max_health=hero_class.base_health,
            current_health=hero_class.base_health,
            max_mana=hero_class.base_mana,
            current_mana=hero_class.base_mana,
            inventory=inventory
        )
        # add some starting items
        sword = Weapon.objects.get_or_create(
            name="Simple Sword",
            defaults={
                'value': 100,
                'attack_bonus': 20,
                'accuracy_bonus': 5,
                'weapon_type': 'sword',
                'equipment_slot': EquipmentSlots.WEAPON
            }
        )[0]
        shield = OffHand.objects.get_or_create(
            name="Wooden Shield",
            defaults={
                'value': 50,
                'block': 5,
                'shield_type': 'wooden',
                'equipment_slot': EquipmentSlots.ACCESSORY
            }
        )[0]
        armor = Armor.objects.get_or_create(
            name="Leather Armor",
            defaults={
                'value': 75,
                'defense_bonus': 10,
                'health_bonus': 25,
                'armor_type': 'leather',
                'equipment_slot': EquipmentSlots.ARMOR
            }
        )[0]
        bow = Weapon.objects.get_or_create(
            name="Simple Bow",
            defaults={
                'value': 100,
                'attack_bonus': 15,
                'accuracy_bonus': 10,
                'weapon_type': 'bow',
                'equipment_slot': EquipmentSlots.WEAPON
            }
        )[0]
        quiver = OffHand.objects.get_or_create(
            name="Quiver of Arrows",
            defaults={
                'value': 30,
                'block': 2,
                'shield_type': 'quiver',
                'equipment_slot': EquipmentSlots.ACCESSORY
            }
        )[0]
        robe = Armor.objects.get_or_create(
            name="Cloth Robe",
            defaults={
                'value': 25,
                'defense_bonus': 5,
                'health_bonus': 10,
                'armor_type': 'cloth',
                'equipment_slot': EquipmentSlots.ARMOR
            }
        )[0]
        staff = Weapon.objects.get_or_create(
            name="Wooden Staff",
            defaults={
                'value': 100,
                'attack_bonus': 8,
                'accuracy_bonus': 15,
                'weapon_type': 'staff',
                'equipment_slot': EquipmentSlots.WEAPON
            }
        )[0]
        spellbook = OffHand.objects.get_or_create(
            name="Beginner's Spellbook",
            defaults={
                'value': 25,
                'block': 0,
                'shield_type': 'tome',
                'equipment_slot': EquipmentSlots.ACCESSORY
            }
        )[0]
        healing_potion = Consumable.objects.get_or_create(
            name="Minor Healing Potion",
            defaults={
                'value': 10,
                'heal_amount': 20,
                'mana_restore': 0,
                'duration': 0
            }
        )[0]
        mana_potion = Consumable.objects.get_or_create(
            name="Minor Mana Potion",
            defaults={
                'value': 10,
                'heal_amount': 0,
                'mana_restore': 20,
                'duration': 0
            }
        )[0]

        if hero_class.name == "Warrior":
            hero.add_to_inventory(sword)
            hero.add_to_inventory(shield)
            hero.add_to_inventory(armor)
            hero.add_to_inventory(healing_potion, quantity=3)
        elif hero_class.name == "Ranger":
            hero.add_to_inventory(bow)
            hero.add_to_inventory(quiver)
            hero.add_to_inventory(armor)
            hero.add_to_inventory(healing_potion, quantity=2)
            hero.add_to_inventory(mana_potion, quantity=1)
        elif hero_class.name == "Wizard":
            hero.add_to_inventory(staff)
            hero.add_to_inventory(spellbook)
            hero.add_to_inventory(robe)
            hero.add_to_inventory(mana_potion, quantity=3)
            hero.add_to_inventory(healing_potion, quantity=1)
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

        if errors:
            raise ValidationError(errors, code="invalid")
