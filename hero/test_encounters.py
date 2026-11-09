import json
from unittest.mock import patch

from django.test import TestCase

from .dungeon import available_encounter_keys, create_run, generate_paths
from .encounters import (
    BattleTier, ENCOUNTER_DEFINITIONS, Encounter, EncounterDefinition, EncounterKind,
)
from .models import Hero, Monster
from battle.models import EncounterMonster


class EncounterTests(TestCase):
    def test_json_round_trip_preserves_instance(self):
        for key in ENCOUNTER_DEFINITIONS:
            with self.subTest(key=key):
                encounter = Encounter.create(key, 4)
                restored = Encounter.from_dict(json.loads(json.dumps(encounter.to_dict())))
                self.assertEqual(restored, encounter)
                self.assertEqual(restored.kind, ENCOUNTER_DEFINITIONS[key].kind)
                self.assertEqual(restored.battle_tier, ENCOUNTER_DEFINITIONS[key].battle_tier)

    def test_invalid_saved_encounters_are_rejected(self):
        valid = Encounter.create('spike_pit', 1).to_dict()
        for changes in ({'floor': 0}, {'floor': True}, {'floor': '1'},
                        {'definition_key': 'unknown'}, {'id': ''}, {'kind': 'trap'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Encounter.from_dict({**valid, **changes})
        for data in (None, {}, []):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Encounter.from_dict(data)

    def test_battle_tier_matches_kind(self):
        for kind, tier in ((EncounterKind.BATTLE, None),
                           (EncounterKind.BATTLE, 'unknown'),
                           (EncounterKind.TRAP, BattleTier.BOSS), ('unknown', None)):
            with self.subTest(kind=kind, tier=tier), self.assertRaises(ValueError):
                EncounterDefinition('test', 'Test', 'Description', kind, tier)

    def test_new_run_selects_from_catalog_and_matches_hero_schema(self):
        for key in available_encounter_keys():
            with self.subTest(key=key), patch('hero.dungeon.random.choice', return_value=key) as choice:
                run = create_run()
                self.assertTrue(Hero().validate_dungeon_data(run))
                encounter = Encounter.from_dict(run['current_encounter'])
                self.assertEqual(encounter.definition_key, key)
                self.assertEqual(encounter.floor, 1)
                self.assertEqual(run['current_floor'], 1)
                self.assertEqual(run['phase'], 'encounter')
                self.assertIsNone(run['path_left'])
                self.assertIsNone(run['path_right'])
                choice.assert_called_once_with(available_encounter_keys())

    def test_selection_excludes_unconfigured_and_oversized_battles(self):
        monster = Monster.objects.create(name='Test monster')
        EncounterMonster.objects.create(encounter_definition_key='level_01_skirmish', monster=monster)
        for position in range(2):
            EncounterMonster.objects.create(encounter_definition_key='ogre_guard',
                                           monster=monster, quantity=2, position_order=position)
        expected = {'level_01_skirmish', 'spike_pit', 'forgotten_cache', 'wandering_healer'}
        self.assertEqual(set(available_encounter_keys()), expected)
        with patch('hero.dungeon.random.choice', side_effect=lambda options: options[0]) as choice:
            run = create_run()
            paths = generate_paths(2)
        for call in choice.call_args_list:
            self.assertEqual(set(call.args[0]), expected)
        self.assertEqual(run['current_encounter']['definition_key'], 'spike_pit')
        self.assertEqual(len(paths), 2)
        # Existing saved encounters still deserialize even after their content is removed.
        self.assertEqual(Encounter.create('goblin_ambush', 1).definition_key, 'goblin_ambush')

    def test_new_run_can_select_a_configured_battle(self):
        monster = Monster.objects.create(name='Briar Rat')
        EncounterMonster.objects.create(encounter_definition_key='level_01_skirmish', monster=monster)
        with patch('hero.dungeon.random.choice', return_value='level_01_skirmish') as choice:
            run = create_run()
        self.assertIn('level_01_skirmish', choice.call_args.args[0])
        self.assertEqual(run['current_encounter']['definition_key'], 'level_01_skirmish')

    @patch('hero.dungeon.random.choice', return_value='spike_pit')
    def test_paths_allow_matching_types_with_distinct_ids(self, choice):
        paths = generate_paths(2)
        left = Encounter.from_dict(paths['path_left'])
        right = Encounter.from_dict(paths['path_right'])
        self.assertEqual(left.kind, EncounterKind.TRAP)
        self.assertEqual(right.kind, EncounterKind.TRAP)
        self.assertEqual(left.floor, 2)
        self.assertEqual(right.floor, 2)
        self.assertNotEqual(left.id, right.id)
        self.assertEqual(choice.call_count, 2)
        options = choice.call_args.args[0]
        self.assertEqual(set(options), set(available_encounter_keys()))
        self.assertEqual(len(options), len(set(options)))
