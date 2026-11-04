from django.test import TestCase
from django.db.utils import IntegrityError
from django.core.exceptions import ValidationError
from hero.models import Hero, HeroClass, Monster, MonsterLoot
from item.models import Item


class HeroModelTest(TestCase):
    def setUp(self):
        # Create a HeroClass for testing
        self.hero_class = HeroClass.objects.create(
            name="Warrior", description="A brave warrior."
        )
        self.hero = Hero.objects.create(
            name="Test Hero", hero_class=self.hero_class, level=1
        )

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

    def test_dungeon_run_store(self):
        from .dungeon import create_run

        run_data = create_run()
        self.hero.store_dungeon_run(run_data)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.dungeon_run, run_data)
        self.assertEqual(self.hero.dungeon_revision, 1)


class HeroClassModelTest(TestCase):
    def setUp(self):
        self.hero_class = HeroClass.objects.create(
            name="Mage", description="A wise mage."
        )

    def test_str_method(self):
        self.assertEqual(str(self.hero_class), "Mage")


class HeroCreationTest(TestCase):
    def test_create_hero(self):
        hero_class = HeroClass.objects.create(
            name="Rogue", description="A stealthy rogue."
        )
        hero = Hero.objects.create(name="New Hero", hero_class=hero_class, level=1)
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


class MonsterModel(TestCase):
    def test_create_monster(self):
        monster = Monster.objects.create(
            name="Goblin",
            level=1,
            current_health=30,
            max_health=30,
            current_mana=10,
            max_mana=10,
            attack=5,
            defense=3,
            magic=2,
            magic_defense=1,
            speed=4,
            accuracy=90,
            evasion=5,
            critical_chance=2,
            critical_damage=1.2,
            threat_level=1,
            experience_reward=15,
        )
        self.assertIsInstance(monster, Monster)
        self.assertEqual(monster.name, "Goblin")
        self.assertEqual(monster.level, 1)
        self.assertEqual(monster.current_health, 30)
        self.assertEqual(monster.max_health, 30)
        self.assertEqual(monster.current_mana, 10)
        self.assertEqual(monster.max_mana, 10)
        self.assertEqual(monster.attack, 5)
        self.assertEqual(monster.defense, 3)
        self.assertEqual(monster.magic, 2)
        self.assertEqual(monster.magic_defense, 1)
        self.assertEqual(monster.speed, 4)
        self.assertEqual(monster.accuracy, 90)
        self.assertEqual(monster.evasion, 5)
        self.assertEqual(monster.critical_chance, 2)
        self.assertEqual(monster.critical_damage, 1.2)
        self.assertEqual(monster.threat_level, 1)
        self.assertEqual(monster.experience_reward, 15)

    def test_monster_threat_level(self):
        monster = Monster.objects.create(
            name="Orc",
            level=5,
            current_health=100,
            max_health=100,
            current_mana=20,
            max_mana=20,
            attack=15,
            defense=10,
            magic=5,
            magic_defense=3,
            speed=8,
            accuracy=85,
            evasion=10,
            critical_chance=3,
            critical_damage=1.3,
            threat_level=3,
            experience_reward=50,
        )
        self.assertEqual(monster.threat_level, 3)

    def test_monster_reject_threat_level_out_of_bounds(self):
        with self.assertRaises(IntegrityError):
            Monster.objects.create(
                name="Dragon",
                level=10,
                current_health=500,
                max_health=500,
                current_mana=100,
                max_mana=100,
                attack=50,
                defense=30,
                magic=20,
                magic_defense=15,
                speed=25,
                accuracy=95,
                evasion=15,
                critical_chance=5,
                critical_damage=2.0,
                threat_level=6,
                experience_reward=200,
            )


class MonsterLootModelTest(TestCase):
    def setUp(self):
        self.item = Item.objects.create(
            name="Rusty Sword", description="An old and rusty sword."
        )
        self.monster = Monster.objects.create(
            name="Skeleton",
            level=2,
            current_health=40,
            max_health=40,
            current_mana=5,
            max_mana=5,
            attack=6,
            defense=4,
            magic=1,
            magic_defense=1,
            speed=3,
            accuracy=80,
            evasion=5,
            critical_chance=1,
            critical_damage=1.1,
            threat_level=1,
            experience_reward=20,
        )

    def test_create_monster_loot(self):
        loot = MonsterLoot.objects.create(
            monster=self.monster, item=self.item, drop_chance=0.5
        )
        self.assertIsInstance(loot, MonsterLoot)
        self.assertEqual(loot.monster, self.monster)
        self.assertEqual(loot.item, self.item)
        self.assertEqual(loot.drop_chance, 0.5)

    def test_monster_loot_invalid_drop_chance(self):
        with self.assertRaises(ValidationError):
            MonsterLoot.objects.create(
                monster=self.monster, item=self.item, drop_chance=-1
            ).clean()
        with self.assertRaises(ValidationError):
            MonsterLoot.objects.create(
                monster=self.monster, item=self.item, drop_chance=101
            ).clean()

    def test_monster_loot_invalid_quantity(self):
        with self.assertRaises(ValidationError):
            MonsterLoot.objects.create(
                monster=self.monster,
                item=self.item,
                drop_chance=1.0,
                min_quantity=5,
                max_quantity=3,
            ).clean()
