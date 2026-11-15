from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MonsterLootQuantityMigrationTest(TransactionTestCase):
    migrate_from = [('hero', '0016_monster_valid_threat_level')]
    migrate_to = [('hero', '0018_monsterloot_monster_loot_min_quantity_positive_and_more')]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Monster = old_apps.get_model('hero', 'Monster')
        MonsterLoot = old_apps.get_model('hero', 'MonsterLoot')
        Item = old_apps.get_model('item', 'Item')

        monster = Monster.objects.create(
            name='Migration test monster',
            experience_reward=-25,
        )
        item = Item.objects.create(name='Migration test item')
        self.loot_ids = [
            MonsterLoot.objects.create(
                monster=monster,
                item=item,
                min_quantity=min_quantity,
                max_quantity=max_quantity,
            ).pk
            for min_quantity, max_quantity in (
                (-1, 1),
                (-2, -1),
                (0, 0),
                (1, 3),
            )
        ]

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        self.MigratedMonsterLoot = new_apps.get_model('hero', 'MonsterLoot')
        self.MigratedMonster = new_apps.get_model('hero', 'Monster')

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_negative_and_zero_quantities_are_normalized_before_field_alterations(self):
        quantities = list(
            self.MigratedMonsterLoot.objects.filter(pk__in=self.loot_ids)
            .order_by('pk')
            .values_list('min_quantity', 'max_quantity')
        )
        self.assertEqual(quantities, [(1, 1), (1, 1), (1, 1), (1, 3)])

    def test_negative_experience_reward_is_normalized_before_field_alteration(self):
        monster = self.MigratedMonster.objects.get(name='Migration test monster')
        self.assertEqual(monster.experience_reward, 0)


class QuadraticExperienceMigrationTest(TransactionTestCase):
    def test_conversion_preserves_levels_stats_and_fractional_progress(self):
        executor = MigrationExecutor(connection)
        before = [('hero', '0027_hero_movement_policy')]
        after = [('hero', '0028_quadratic_experience')]
        executor.migrate(before)
        self.addCleanup(self.restore_latest)
        apps = executor.loader.project_state(before).apps
        Hero = apps.get_model('hero', 'Hero')
        HeroClass = apps.get_model('hero', 'HeroClass')
        hero_class = HeroClass.objects.create(name='Migration class')
        cases = [(1, 50, 50), (2, 150, 200), (12, 1198, 7776),
                 (5, 400, 1000), (5, 300, 1000), (2, 350, 600), (0, 25, 25)]
        ids = []
        for index, (level, xp, expected) in enumerate(cases):
            ids.append(Hero.objects.create(name=f'Curve hero {index}',
                hero_class=hero_class, level=level, experience=xp,
                attack=37, current_health=23, current_mana=11).pk)
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        Hero = executor.loader.project_state(after).apps.get_model('hero', 'Hero')
        for pk, (level, xp, expected) in zip(ids, cases):
            hero = Hero.objects.get(pk=pk)
            self.assertEqual((hero.level, hero.experience), (level, expected))
            self.assertEqual((hero.attack, hero.current_health, hero.current_mana), (37, 23, 11))
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        Hero = executor.loader.project_state(before).apps.get_model('hero', 'Hero')
        for pk, (level, xp, expected) in zip(ids, cases):
            self.assertEqual(Hero.objects.get(pk=pk).experience,
                             max(xp, 100 * (level - 1)) if level > 0 else xp)

    def restore_latest(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
