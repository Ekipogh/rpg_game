import copy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from django.conf import settings
from django.core.management import call_command, CommandError
from django.test import TestCase

from battle.models import EncounterMonster
from hero.encounters import Encounter
from hero.models import Hero, HeroClass, HeroClassEquipment, Monster, MonsterLoot
from hero.creation import create_character
from item.models import Item, Instant


class ContentImportTests(TestCase):
    def run_import(self, **kwargs):
        call_command("import_rpg_content", stdout=StringIO(), **kwargs)

    def test_full_catalog_rerun_and_coins(self):
        self.run_import()
        self.assertEqual(set(HeroClass.objects.values_list('name', flat=True)), {'Warrior', 'Ranger', 'Wizard'})
        self.assertEqual(HeroClass.objects.get(name='Wizard').mag_gain_max, 4)
        self.assertEqual(HeroClassEquipment.objects.count(), 9)
        self.assertEqual(Item.objects.count(), 235)
        self.assertEqual(Monster.objects.count(), 48)
        self.assertEqual(MonsterLoot.objects.count(), 452)
        self.assertEqual(EncounterMonster.objects.count(), 88)
        self.assertEqual(HeroClassEquipment.objects.count(), 9)
        ids = dict(Item.objects.values_list("name", "pk"))
        Monster.objects.filter(name="Briar Rat").update(attack=999)
        self.run_import()
        self.assertEqual(dict(Item.objects.values_list("name", "pk")), ids)
        self.assertEqual(MonsterLoot.objects.count(), 452)
        self.assertEqual(EncounterMonster.objects.count(), 88)
        self.assertEqual(Monster.objects.get(name="Briar Rat").attack, 12)
        for name, amount in (("Copper Coin", 1), ("Silver Coin", 10), ("Gold Coin", 100)):
            coin = Item.objects.get(name=name)
            self.assertIsInstance(coin, Instant)
            self.assertEqual(coin.money_amount, amount)
            self.assertEqual(coin.heal_amount, 0)
        self.assertEqual(Encounter.create("level_20_champion", 20).battle_tier, "boss")

    def test_dry_run_does_not_write(self):
        self.run_import(dry_run=True)
        self.assertEqual(Item.objects.count(), 0)
        self.assertEqual(Monster.objects.count(), 0)
        self.assertEqual(MonsterLoot.objects.count(), 0)
        self.assertEqual(EncounterMonster.objects.count(), 0)
        self.assertEqual(HeroClass.objects.count(), 0)
        self.assertEqual(HeroClassEquipment.objects.count(), 0)

    def test_imported_loadout_is_equipped_on_new_heroes(self):
        self.run_import()
        data = yaml.safe_load((Path(settings.BASE_DIR) / 'rpg_content.yaml').read_text(encoding='utf-8'))
        names = {item['key']: item['name'] for item in data['items']}
        for row in data['hero_classes']:
            hero_class = HeroClass.objects.get(name=row['name'])
            hero = create_character(f"New {row['name']}", hero_class)
            self.assertEqual(dict(hero.equipment.slots.values_list('slot', 'item__name')),
                             {slot: names[key] for slot, key in row['initial_equipment'].items()})
            self.assertEqual(hero.attack, hero_class.base_attack)
            self.assertEqual(hero.attack_mod, hero.weapon.attack_bonus)
            self.assertEqual(hero.inventory.all().count(), 0)
        self.assertEqual(Item.objects.count(), 235)

    def test_invalid_loadouts_roll_back_import(self):
        data = yaml.safe_load((Path(settings.BASE_DIR) / 'rpg_content.yaml').read_text(encoding='utf-8'))
        for equipment in ({'weapon': 'missing'}, {'weapon': 'healing_draught_1'},
                          {'unknown': 'rustleaf_blade'}, {'weapon': 'briarwood_wizard_1_weapon'},
                          {'weapon': 'briar_spear'}):
            invalid = copy.deepcopy(data)
            invalid['hero_classes'][0]['initial_equipment'] = equipment
            with TemporaryDirectory() as directory:
                path = Path(directory) / 'invalid.yaml'
                path.write_text(yaml.safe_dump(invalid), encoding='utf-8')
                with self.assertRaises(CommandError):
                    self.run_import(path=str(path))
            self.assertEqual(Item.objects.count(), 0)
            self.assertEqual(HeroClassEquipment.objects.count(), 0)
            self.assertEqual(HeroClass.objects.count(), 0)

    def test_loadout_rerun_replaces_config_without_changing_existing_hero(self):
        self.run_import()
        warrior = HeroClass.objects.get(name='Warrior')
        hero = create_character('Existing', warrior)
        data = yaml.safe_load((Path(settings.BASE_DIR) / 'rpg_content.yaml').read_text(encoding='utf-8'))
        data['hero_classes'][0]['initial_equipment'] = {}
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'changed.yaml'
            path.write_text(yaml.safe_dump(data), encoding='utf-8')
            self.run_import(path=str(path))
        self.assertEqual(warrior.initial_equipment.count(), 0)
        self.assertEqual(hero.equipment.slots.count(), 3)

    def test_retained_loadouts_reject_incompatible_item_updates(self):
        self.run_import()
        data = yaml.safe_load((Path(settings.BASE_DIR) / 'rpg_content.yaml').read_text(encoding='utf-8'))
        blade = next(item for item in data['items'] if item['key'] == 'rustleaf_blade')
        classes = copy.deepcopy(data['hero_classes'])
        for row in classes:
            row.pop('initial_equipment')
        original_loadouts = list(HeroClassEquipment.objects.order_by('pk').values())
        updates = ({'level_requirement': 2}, {'hero_class_restriction': 'wizard'},
                   {'equipment_slot': 'armor'})
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'changed.yaml'
            for update in updates:
                changed = copy.deepcopy(blade)
                changed.update(update)
                catalog = dict(schema_version=1, hero_classes=classes, items=[changed],
                               monsters=[], monster_loot=[], encounters=[])
                path.write_text(yaml.safe_dump(catalog), encoding='utf-8')
                for dry_run in (False, True):
                    with self.subTest(update=update, dry_run=dry_run):
                        with self.assertRaises(CommandError):
                            self.run_import(path=str(path), dry_run=dry_run)
                        item = Item.objects.get(name=blade['name'])
                        self.assertEqual(item.level_requirement, 1)
                        self.assertEqual(item.equipment_slot, 'weapon')
                        self.assertEqual(item.hero_class_restriction.name, 'Warrior')
                        self.assertEqual(list(HeroClassEquipment.objects.order_by('pk').values()), original_loadouts)
        hero = create_character('Still playable', HeroClass.objects.get(name='Warrior'))
        self.assertEqual(hero.weapon.name, blade['name'])

    def test_item_updates_validate_loadouts_of_omitted_classes(self):
        self.run_import()
        blade = Item.objects.get(name='Rustleaf Blade')
        catalog = dict(schema_version=1, items=[dict(key='rustleaf_blade', model='Weapon',
                       name=blade.name, level_requirement=2)], monsters=[], monster_loot=[], encounters=[])
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'changed.yaml'
            path.write_text(yaml.safe_dump(catalog), encoding='utf-8')
            for dry_run in (False, True):
                with self.subTest(dry_run=dry_run), self.assertRaises(CommandError):
                    self.run_import(path=str(path), dry_run=dry_run)
        blade.refresh_from_db()
        self.assertEqual(blade.level_requirement, 1)

    def test_final_loadout_can_remove_item_made_ineligible(self):
        self.run_import()
        catalog = dict(schema_version=1,
            hero_classes=[dict(key='warrior', name='Warrior', initial_equipment={})],
            items=[dict(key='rustleaf_blade', model='Weapon', name='Rustleaf Blade', level_requirement=2)],
            monsters=[], monster_loot=[], encounters=[])
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'changed.yaml'
            path.write_text(yaml.safe_dump(catalog), encoding='utf-8')
            self.run_import(path=str(path))
        self.assertEqual(Item.objects.get(name='Rustleaf Blade').level_requirement, 2)
        self.assertEqual(HeroClass.objects.get(name='Warrior').initial_equipment.count(), 0)

    def test_existing_class_identity_image_and_hero_are_preserved(self):
        warrior = HeroClass.objects.create(name='Warrior', base_attack=999, image='hero_classes/custom.png')
        hero = Hero.objects.create(name='Veteran', hero_class=warrior, attack=123)
        for _ in range(2):
            self.run_import()
        warrior.refresh_from_db()
        hero.refresh_from_db()
        self.assertEqual(HeroClass.objects.get(name='Warrior').pk, warrior.pk)
        self.assertEqual(warrior.base_attack, 15)
        self.assertEqual(warrior.image.name, 'hero_classes/warrior.png')
        self.assertEqual((hero.hero_class_id, hero.attack), (warrior.pk, 123))
        self.assertEqual(HeroClass.objects.count(), 3)

    def test_duplicate_existing_class_names_are_rejected(self):
        for _ in range(2):
            HeroClass.objects.create(name='Warrior', base_attack=999)
        with self.assertRaisesMessage(CommandError, 'Multiple existing hero classes'):
            self.run_import()
        self.assertEqual(HeroClass.objects.filter(base_attack=999).count(), 2)
        self.assertEqual(Item.objects.count(), 0)

    def test_optional_classes_and_invalid_growth(self):
        data = yaml.safe_load((Path(settings.BASE_DIR) /
            'rpg_content.yaml').read_text(encoding='utf-8'))
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'content.yaml'
            for lower, upper in ((4, 2), (-1, 2), (True, 2)):
                invalid = copy.deepcopy(data)
                invalid['hero_classes'][-1].update(atk_gain_min=lower, atk_gain_max=upper)
                path.write_text(yaml.safe_dump(invalid), encoding='utf-8')
                with self.assertRaisesMessage(CommandError, 'growth range'):
                    self.run_import(path=str(path))
                self.assertEqual(HeroClass.objects.count(), 0)
            del data['hero_classes']
            for item in data['items']:
                item.pop('hero_class_restriction', None)
            path.write_text(yaml.safe_dump(data), encoding='utf-8')
            self.run_import(path=str(path))
            self.assertEqual(HeroClass.objects.count(), 0)
            self.assertEqual(Item.objects.count(), 235)

    def test_invalid_late_reference_rolls_back(self):
        data = yaml.safe_load((Path(settings.BASE_DIR) /
            "rpg_content.yaml").read_text(encoding="utf-8"))
        for mutation in ("reference", "quantity", "type"):
            invalid = copy.deepcopy(data)
            if mutation == "reference":
                invalid["encounters"][-1]["enemies"][0]["monster"] = "missing"
            elif mutation == "quantity":
                invalid["encounters"][-1]["enemies"][0]["quantity"] = 4
            else:
                Item.objects.create(name="Rustleaf Blade")
            with TemporaryDirectory() as directory:
                path = Path(directory) / "invalid.yaml"
                path.write_text(yaml.safe_dump(invalid), encoding="utf-8")
                with self.assertRaises(CommandError):
                    self.run_import(path=str(path))
            self.assertEqual(Monster.objects.count(), 0)
            self.assertEqual(HeroClass.objects.count(), 0)
            self.assertEqual(Item.objects.count(), 1 if mutation == "type" else 0)
