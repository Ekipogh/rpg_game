from django.test import TestCase
from hero.models import Hero, HeroClass


class HeroModelTest(TestCase):
    def setUp(self):
        # Create a HeroClass for testing
        self.hero_class = HeroClass.objects.create(
            name="Warrior", description="A brave warrior.")
        self.hero = Hero.objects.create(
            name="Test Hero", hero_class=self.hero_class, level=1)

    def test_level_up(self):
        """Test that level up increases stats according to class bonuses"""
        initial_level = self.hero.level
        initial_attack = self.hero.attack
        initial_health = self.hero.max_health
        initial_mana = self.hero.max_mana

        self.hero.level_up()

        self.assertEqual(self.hero.level, initial_level + 1)
        self.assertGreater(self.hero.attack, initial_attack)
        self.assertGreater(self.hero.max_health, initial_health)
        self.assertGreaterEqual(self.hero.max_mana, initial_mana)
        self.assertEqual(self.hero.current_health, self.hero.max_health)
        self.assertEqual(self.hero.current_mana, self.hero.max_mana)

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
        self.hero.max_health = 200
        self.hero.current_health = 100
        self.assertEqual(self.hero.health_percentage, 50)
        self.hero.current_health = 200
        self.assertEqual(self.hero.health_percentage, 100)
        self.hero.current_health = 0
        self.assertEqual(self.hero.health_percentage, 0)
        self.hero.max_health = 0
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
        self.hero.current_health = self.hero.max_health
        self.hero.take_damage(10)
        self.assertTrue(self.hero.current_health < self.hero.max_health)

    def test_take_damage_no_healing_if_full_health(self):
        self.hero.current_health = self.hero.max_health
        self.hero.take_damage(0)
        self.assertEqual(self.hero.current_health, self.hero.max_health)

    def test_heal(self):
        self.hero.current_health = 50
        self.hero.heal(30)
        self.assertEqual(self.hero.current_health, 80)
        # Test that health does not exceed max health
        self.hero.heal(200)
        self.assertEqual(self.hero.current_health, self.hero.max_health)

    def test_heal_no_effect_if_full_health(self):
        self.hero.current_health = self.hero.max_health
        self.hero.heal(10)
        self.assertEqual(self.hero.current_health, self.hero.max_health)

    def test_health_regeneration_rate(self):
        """Test health regeneration rate is 1% of max HP"""
        self.hero.max_health = 100
        self.assertEqual(self.hero.health_regeneration_rate, 1)

        self.hero.max_health = 500
        self.assertEqual(self.hero.health_regeneration_rate, 5)

        self.hero.max_health = 1000
        self.assertEqual(self.hero.health_regeneration_rate, 10)

    def test_mana_regeneration_rate(self):
        """Test mana regeneration rate is 1% of max MP"""
        self.hero.max_mana = 100
        self.assertEqual(self.hero.mana_regeneration_rate, 1)

        self.hero.max_mana = 500
        self.assertEqual(self.hero.mana_regeneration_rate, 5)

        self.hero.max_mana = 1000
        self.assertEqual(self.hero.mana_regeneration_rate, 10)

    def test_mana_percentage(self):
        """Test mana percentage calculation"""
        self.hero.max_mana = 100
        self.hero.current_mana = 50
        self.assertEqual(self.hero.mana_percentage, 50)

        self.hero.current_mana = 100
        self.assertEqual(self.hero.mana_percentage, 100)

        self.hero.current_mana = 0
        self.assertEqual(self.hero.mana_percentage, 0)

        self.hero.max_mana = 0
        self.assertEqual(self.hero.mana_percentage, 0)

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
        self.assertEqual(hero.current_health, hero.max_health)
        self.assertEqual(hero.experience, 0)
        self.assertEqual(hero.attack, 10)
        self.assertEqual(hero.defense, 10)
        self.assertEqual(hero.magic, 10)
        self.assertEqual(hero.magic_defense, 10)
        self.assertEqual(hero.speed, 10)
        self.assertEqual(hero.accuracy, 100)
        self.assertEqual(hero.evasion, 0)
        self.assertEqual(hero.critical_chance, 5)
        self.assertEqual(hero.critical_damage, 1.5)