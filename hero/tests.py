from django.test import TestCase
from django.db.utils import IntegrityError
from django.db import transaction
from django.core.exceptions import ValidationError
from hero.models import Hero, HeroClass, Monster, MonsterLoot
from item.models import Item
from decimal import Decimal


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
    def test_monster_stats_match_hero_defaults(self):
        hero = Hero()
        monster = Monster.objects.create(name="Goblin")

        stat_fields = (
            "max_health",
            "current_health",
            "max_mana",
            "current_mana",
            "attack",
            "defense",
            "magic",
            "magic_defense",
            "speed",
            "accuracy",
            "evasion",
            "critical_chance",
            "critical_damage",
        )
        for field in stat_fields:
            with self.subTest(field=field):
                self.assertEqual(getattr(monster, field), getattr(hero, field))

        self.assertEqual(monster.level, 1)
        self.assertEqual(monster.experience_reward, 0)
        self.assertEqual(monster.threat_level, "common")
        self.assertEqual(monster.monster_class, "warrior")

    def test_allowed_threat_levels(self):
        for threat_level in ("common", "miniboss", "boss"):
            with self.subTest(threat_level=threat_level):
                monster = Monster.objects.create(
                    name=f"{threat_level} monster", threat_level=threat_level
                )
                self.assertEqual(monster.threat_level, threat_level)

    def test_invalid_threat_level_is_rejected(self):
        monster = Monster(name="Invalid monster", threat_level="elite")
        with self.assertRaises(ValidationError):
            monster.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Monster.objects.create(
                    name="Invalid DB monster", threat_level="elite"
                )

    def test_negative_experience_reward_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Monster.objects.create(name="Negative XP monster", experience_reward=-1)


class MonsterLootModelTest(TestCase):
    def setUp(self):
        self.item = Item.objects.create(
            name="Rusty Sword", description="An old and rusty sword."
        )
        self.monster = Monster.objects.create(
            name="Skeleton",
            level=2,
            threat_level="common",
            experience_reward=20,
        )

    def test_create_monster_loot(self):
        loot = MonsterLoot.objects.create(
            monster=self.monster, item=self.item, drop_chance=12.5
        )
        self.assertIsInstance(loot, MonsterLoot)
        self.assertEqual(loot.monster, self.monster)
        self.assertEqual(loot.item, self.item)
        self.assertEqual(loot.drop_chance, Decimal("12.50"))
        self.assertEqual(loot.min_quantity, 1)
        self.assertEqual(loot.max_quantity, 1)
        self.assertEqual(list(self.monster.loot.all()), [loot])

    def test_monster_loot_invalid_drop_chance(self):
        with self.assertRaises(ValidationError):
            MonsterLoot(
                monster=self.monster, item=self.item, drop_chance=-1
            ).full_clean()
        with self.assertRaises(ValidationError):
            MonsterLoot(
                monster=self.monster, item=self.item, drop_chance=101
            ).full_clean()

    def test_monster_loot_drop_chance_database_constraint(self):
        for drop_chance in (-1, 101):
            with self.subTest(drop_chance=drop_chance):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        MonsterLoot.objects.create(
                            monster=self.monster,
                            item=self.item,
                            drop_chance=drop_chance,
                        )

    def test_monster_loot_invalid_quantity(self):
        with self.assertRaises(ValidationError):
            MonsterLoot(
                monster=self.monster,
                item=self.item,
                drop_chance=1,
                min_quantity=5,
                max_quantity=3,
            ).full_clean()
        with self.assertRaises(ValidationError):
            MonsterLoot(
                monster=self.monster,
                item=self.item,
                min_quantity=0,
            ).full_clean()

    def test_monster_loot_quantity_database_constraint(self):
        invalid_quantities = ((0, 1), (1, 0), (5, 3))
        for min_quantity, max_quantity in invalid_quantities:
            with self.subTest(min_quantity=min_quantity, max_quantity=max_quantity):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        MonsterLoot.objects.create(
                            monster=self.monster,
                            item=self.item,
                            min_quantity=min_quantity,
                            max_quantity=max_quantity,
                        )
