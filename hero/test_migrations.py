from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MonsterLootQuantityMigrationTest(TransactionTestCase):
    migrate_from = [('hero', '0017_remove_monster_valid_threat_level_and_more')]
    migrate_to = [('hero', '0018_monsterloot_monster_loot_min_quantity_positive_and_more')]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Monster = old_apps.get_model('hero', 'Monster')
        MonsterLoot = old_apps.get_model('hero', 'MonsterLoot')
        Item = old_apps.get_model('item', 'Item')

        monster = Monster.objects.create(name='Migration test monster')
        item = Item.objects.create(name='Migration test item')
        self.loot_ids = [
            MonsterLoot.objects.create(
                monster=monster,
                item=item,
                min_quantity=min_quantity,
                max_quantity=max_quantity,
            ).pk
            for min_quantity, max_quantity in ((0, 1), (0, 0), (1, 3))
        ]

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        self.MigratedMonsterLoot = new_apps.get_model('hero', 'MonsterLoot')

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_quantities_are_normalized_before_constraints(self):
        quantities = list(
            self.MigratedMonsterLoot.objects.filter(pk__in=self.loot_ids)
            .order_by('pk')
            .values_list('min_quantity', 'max_quantity')
        )
        self.assertEqual(quantities, [(1, 1), (1, 1), (1, 3)])
