from pathlib import Path
import yaml
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.template.loader import render_to_string
from item.models import Accessory
from item.views import serialize_inventory_item


class AccessoryResistanceTests(TestCase):
    def test_validation_and_historical_names(self):
        for value in ([], None, True, {'burning': True}, {'burning': -1}, {'burning': 101}, {'burning': 1.5}, {'poison': 50}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Accessory(name='Invalid', status_resistances=value).full_clean()
        for value in ({}, {'burning': 0}, {'chilled': 100}):
            Accessory(name='Valid', status_resistances=value).full_clean()
        historical = Accessory.objects.create(name='Legacy', status_resistances={'poison': 100})
        historical.full_clean()
        historical.status_resistances['unknown'] = 10
        with self.assertRaises(ValidationError):
            historical.full_clean()

    def test_display_and_serialization(self):
        item = Accessory(name='Ward', status_resistances={'static_charge': 25})
        self.assertIn('Static Charge 25%', item.get_stats())
        self.assertEqual(serialize_inventory_item(item)['status_resistances'], {'static_charge': 25})
        html = render_to_string('item/detail.html', {'item': item})
        self.assertIn('Static Charge Resistance', html)
        self.assertIn('25%', html)
        self.assertIn('class="accessory-stats"', html)

    def test_catalog_has_explicit_themed_progression(self):
        text = (Path(settings.BASE_DIR) / 'rpg_content.yaml').read_text(encoding='utf-8')
        self.assertNotIn('status_immunities', text)
        items = [row for row in yaml.safe_load(text)['items'] if row['model'] == 'Accessory']
        self.assertEqual(len(items), 72)
        themes = {1: ('gust',), 2: ('gust',), 3: ('chilled',), 4: ('stagger',), 5: ('stagger',),
                  6: ('withering',), 7: ('chilled', 'frozen'), 8: ('burning',), 9: ('burning',),
                  10: ('static_charge',), 11: ('withering',), 12: ('burning', 'chilled', 'static_charge'),
                  13: ('stagger',), 14: ('gust',), 15: ('withering',), 16: ('static_charge',),
                  17: ('withering',), 18: ('withering',), 19: ('burning', 'withering'),
                  20: ('burning', 'chilled', 'frozen', 'static_charge', 'stagger', 'gust', 'withering')}
        for item in items:
            level = item['level_requirement']
            self.assertEqual(item['status_resistances'], {name: 5 + 35 * (level - 1) // 19 for name in themes[level]})



class ResistanceMigrationTests(TransactionTestCase):
    def test_legacy_immunities_are_preserved_as_percentages(self):
        old = [('item', '0018_alter_accessory_options_alter_armor_options_and_more')]
        executor = MigrationExecutor(connection)
        try:
            executor.migrate(old)
            apps = executor.loader.project_state(old).apps
            Accessory = apps.get_model('item', 'Accessory')
            ContentType = apps.get_model('contenttypes', 'ContentType')
            ct, _ = ContentType.objects.get_or_create(app_label='item', model='accessory')
            cases = [([], {}), (['burn', 'frozen', 'poison'], {'burning': 100, 'frozen': 100, 'poison': 100}),
                     (['burn', 'burning'], {'burning': 100})]
            ids = [Accessory.objects.create(name=f'Legacy ward {i}', polymorphic_ctype_id=ct.pk,
                                           status_immunities=values).pk for i, (values, _) in enumerate(cases)]
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from item.models import Accessory as CurrentAccessory
            for pk, (_, expected) in zip(ids, cases):
                accessory = CurrentAccessory.objects.get(pk=pk)
                self.assertEqual(accessory.status_resistances, expected)
                accessory.full_clean()
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
