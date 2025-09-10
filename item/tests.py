from django.test import TestCase
from hero.models import HeroClass
from item.models import Item, EquipmentSlots, Weapon, Armor, OfHand, Consumable

# Create your tests here.
class ItemTests(TestCase):
    def test_create_weapon(self):
        weapon = Weapon.objects.create(name="Sword of Testing", damage=15, weapon_type="sword")
        self.assertEqual(weapon.name, "Sword of Testing")
        self.assertEqual(weapon.damage, 15)
        self.assertEqual(weapon.weapon_type, "sword")
        self.assertEqual(weapon.equipment_slot, EquipmentSlots.WEAPON.value)

    def test_create_armor(self):
        armor = Armor.objects.create(name="Shield of Testing", defense=10, armor_type="plate")
        self.assertEqual(armor.name, "Shield of Testing")
        self.assertEqual(armor.defense, 10)
        self.assertEqual(armor.armor_type, "plate")
        self.assertEqual(armor.equipment_slot, EquipmentSlots.HEAD.value)

    def test_create_ofhand(self):
        ofhand = OfHand.objects.create(name="Buckler of Testing", block=8, shield_type="wooden")
        self.assertEqual(ofhand.name, "Buckler of Testing")
        self.assertEqual(ofhand.block, 8)
        self.assertEqual(ofhand.shield_type, "wooden")
        self.assertEqual(ofhand.equipment_slot, EquipmentSlots.SHIELD.value)

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
        self.assertFalse(hasattr(item, 'damage'))
        self.assertFalse(hasattr(item, 'defense'))

    def test_equipment_slot_choices(self):
        expected_choices = [
            (EquipmentSlots.HEAD.value, 'Head'),
            (EquipmentSlots.CHEST.value, 'Chest'),
            (EquipmentSlots.LEGS.value, 'Legs'),
            (EquipmentSlots.FEET.value, 'Feet'),
            (EquipmentSlots.HANDS.value, 'Hands'),
            (EquipmentSlots.WEAPON.value, 'Weapon'),
            (EquipmentSlots.SHIELD.value, 'Shield'),
        ]
        self.assertEqual(EquipmentSlots.choices(), expected_choices)

    def test_consumable_use_heal(self):
        from hero.models import Hero, HeroClass  # Import here to avoid circular imports
        hero_class = HeroClass.objects.create(name="Warrior", description="A brave warrior.")
        hero = Hero.objects.create(name="Test Hero", constitution=10, level=1, hero_class=hero_class)
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
        hero = Hero.objects.create(name="Test Hero", constitution=10, level=1, hero_class=hero_class)
        hero.max_mana = 100
        hero.current_mana = 40
        hero.save()

        consumable = Consumable.objects.create(name="Mana Potion", heal_amount=0, mana_restore=50, duration=0)
        consumable.use(hero)

        hero.refresh_from_db()
        self.assertEqual(hero.current_mana, 90)  # Restored by 50 but capped at max_mana