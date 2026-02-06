from django.test import TestCase
from hero.models import HeroClass
from item.models import Item, EquipmentSlots, Weapon, Armor, OffHand, Consumable, Accessory

# Create your tests here.
class ItemTests(TestCase):
    def test_create_weapon(self):
        weapon = Weapon.objects.create(name="Sword of Testing", attack_bonus=15, accuracy_bonus=5, weapon_type="sword")
        self.assertEqual(weapon.name, "Sword of Testing")
        self.assertEqual(weapon.attack_bonus, 15)
        self.assertEqual(weapon.accuracy_bonus, 5)
        self.assertEqual(weapon.weapon_type, "sword")
        self.assertEqual(weapon.equipment_slot, EquipmentSlots.WEAPON.value)

    def test_create_armor(self):
        armor = Armor.objects.create(name="Plate Armor of Testing", defense_bonus=10, health_bonus=50, armor_type="plate")
        self.assertEqual(armor.name, "Plate Armor of Testing")
        self.assertEqual(armor.defense_bonus, 10)
        self.assertEqual(armor.health_bonus, 50)
        self.assertEqual(armor.armor_type, "plate")
        self.assertEqual(armor.equipment_slot, EquipmentSlots.ARMOR.value)

    def test_create_offhand(self):
        offhand = OffHand.objects.create(name="Buckler of Testing", block=8, shield_type="wooden")
        self.assertEqual(offhand.name, "Buckler of Testing")
        self.assertEqual(offhand.block, 8)
        self.assertEqual(offhand.shield_type, "wooden")
        self.assertEqual(offhand.equipment_slot, EquipmentSlots.ACCESSORY.value)

    def test_create_consumable_health(self):
        consumable = Consumable.objects.create(name="Health Potion", heal_amount=50, mana_restore=0, duration=0)
        self.assertEqual(consumable.name, "Health Potion")
        self.assertEqual(consumable.heal_amount, 50)
        self.assertEqual(consumable.mana_restore, 0)
        self.assertEqual(consumable.duration, 0)

    def test_create_consumable_mana(self):
        consumable = Consumable.objects.create(name="Mana Potion", heal_amount=0, mana_restore=30, duration=0)
        self.assertEqual(consumable.name, "Mana Potion")
        self.assertEqual(consumable.heal_amount, 0)
        self.assertEqual(consumable.mana_restore, 30)
        self.assertEqual(consumable.duration, 0)

    def test_create_generic_item(self):
        item = Item.objects.create(name="Generic Item", description="Just a test item", value=5)
        self.assertEqual(item.name, "Generic Item")
        self.assertEqual(item.description, "Just a test item")
        self.assertEqual(item.value, 5)
        self.assertIsNone(item.hero_class_restriction)
        self.assertFalse(hasattr(item, 'attack_bonus'))
        self.assertFalse(hasattr(item, 'defense_bonus'))

    def test_create_accessory(self):
        accessory = Accessory.objects.create(
            name="Lucky Ring",
            critical_bonus=5,
            status_immunities=["poison"],
            accessory_type="ring"
        )
        self.assertEqual(accessory.name, "Lucky Ring")
        self.assertEqual(accessory.critical_bonus, 5)
        self.assertEqual(accessory.status_immunities, ["poison"])
        self.assertEqual(accessory.equipment_slot, EquipmentSlots.ACCESSORY.value)

    def test_equipment_slot_choices(self):
        expected_choices = [
            (EquipmentSlots.WEAPON.value, 'Weapon'),
            (EquipmentSlots.ARMOR.value, 'Armor'),
            (EquipmentSlots.ACCESSORY.value, 'Accessory'),
        ]
        self.assertEqual(EquipmentSlots.choices(), expected_choices)

    def test_consumable_use_heal(self):
        from hero.models import Hero, HeroClass  # Import here to avoid circular imports
        hero_class = HeroClass.objects.create(name="Warrior", description="A brave warrior.")
        hero = Hero.objects.create(name="Test Hero", level=1, hero_class=hero_class)
        hero.max_health = 100
        hero.current_health = 50
        hero.save()

        consumable = Consumable.objects.create(name="Health Potion", heal_amount=30, mana_restore=0, duration=0)
        consumable.use(hero)

        hero.refresh_from_db()
        self.assertEqual(hero.current_health, 80)  # Healed by 30

    def test_consumable_use_mana(self):
        from hero.models import Hero, HeroClass  # Import here to avoid circular imports
        hero_class = HeroClass.objects.create(name="Warrior", description="A brave warrior.")
        hero = Hero.objects.create(name="Test Hero", level=1, hero_class=hero_class)
        hero.max_mana = 100
        hero.current_mana = 40
        hero.save()

        consumable = Consumable.objects.create(name="Mana Potion", heal_amount=0, mana_restore=50, duration=0)
        consumable.use(hero)

        hero.refresh_from_db()
        self.assertEqual(hero.current_mana, 90)  # Restored by 50