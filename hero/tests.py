from django.test import TestCase
from hero.models import Hero, HeroClass


class HeroModelTest(TestCase):
    def setUp(self):
        # Create a HeroClass for testing
        self.hero_class = HeroClass.objects.create(
            name="Warrior", description="A brave warrior.")
        self.hero = Hero.objects.create(
            name="Test Hero", hero_class=self.hero_class, level=1)

    def test_calculate_max_health(self):
        expected_health = self.hero_class.base_health + \
            (self.hero.constitution - 10) * 2 + (self.hero.level - 1) * 5
        self.assertEqual(self.hero.calculate_max_health(), expected_health)

    def test_update_health(self):
        self.hero.constitution = 15
        self.hero.level = 3
        self.hero.update_health()
        expected_health = self.hero.calculate_max_health()
        self.assertEqual(self.hero.health, expected_health)
        self.assertEqual(self.hero.current_health, expected_health)

    def test_experience_percentage(self):
        self.hero.experience = 50
        self.assertEqual(self.hero.experience_percentage, 50)
        self.hero.experience = 150
        self.assertEqual(self.hero.experience_percentage, 100)
        self.hero.experience = 0
        self.assertEqual(self.hero.experience_percentage, 0)
        self.hero.level = 0
        self.assertEqual(self.hero.experience_percentage, 0)

    def test_health_percentage(self):
        self.hero.health = 200
        self.hero.current_health = 100
        self.assertEqual(self.hero.health_percentage, 50)
        self.hero.current_health = 200
        self.assertEqual(self.hero.health_percentage, 100)
        self.hero.current_health = 0
        self.assertEqual(self.hero.health_percentage, 0)
        self.hero.health = 0
        self.assertEqual(self.hero.health_percentage, 0)

    def test_take_damage(self):
        initial_health = self.hero.current_health
        damage = 20
        self.hero.take_damage(damage)
        self.assertEqual(self.hero.current_health, initial_health - damage)
        # Test that health does not go below 0
        self.hero.take_damage(200)
        self.assertEqual(self.hero.current_health, 0)

    def test_take_damage_starts_healing(self):
        self.hero.current_health = self.hero.health
        self.hero.take_damage(10)
        self.assertTrue(self.hero.current_health < self.hero.health)

    def test_take_damage_no_healing_if_full_health(self):
        self.hero.current_health = self.hero.health
        self.hero.take_damage(0)
        self.assertEqual(self.hero.current_health, self.hero.health)

    def test_heal(self):
        self.hero.current_health = 50
        self.hero.heal(30)
        self.assertEqual(self.hero.current_health, 80)
        # Test that health does not exceed max health
        self.hero.heal(200)
        self.assertEqual(self.hero.current_health, self.hero.health)

    def test_heal_no_effect_if_full_health(self):
        self.hero.current_health = self.hero.health
        self.hero.heal(10)
        self.assertEqual(self.hero.current_health, self.hero.health)

    def test_str_method(self):
        self.assertEqual(str(self.hero), "Test Hero")
        self.assertEqual(str(self.hero_class), "Warrior")

class HeroClassModelTest(TestCase):
    def setUp(self):
        self.hero_class = HeroClass.objects.create(
            name="Mage", description="A wise mage.")

    def test_str_method(self):
        self.assertEqual(str(self.hero_class), "Mage")

class HeroCreationTest(TestCase):
    def test_create_hero(self):
        hero_class = HeroClass.objects.create(
            name="Rogue", description="A stealthy rogue.")
        hero = Hero.objects.create(
            name="New Hero", hero_class=hero_class, level=1)
        self.assertIsInstance(hero, Hero)
        self.assertEqual(hero.name, "New Hero")
        self.assertEqual(hero.hero_class, hero_class)
        self.assertEqual(hero.level, 1)
        self.assertEqual(hero.current_health, hero.health)
        self.assertEqual(hero.experience, 0)
        self.assertEqual(hero.strength, 10)
        self.assertEqual(hero.constitution, 10)
        self.assertEqual(hero.agility, 10)
        self.assertEqual(hero.intelligence, 10)