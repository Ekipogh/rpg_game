import json
from unittest.mock import patch

from django.test import SimpleTestCase

from .dungeon import create_run, generate_paths
from .encounters import (
    BattleTier, ENCOUNTER_DEFINITIONS, Encounter, EncounterDefinition, EncounterKind,
)
from .models import Hero


class EncounterTests(SimpleTestCase):
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

    def test_new_run_starts_with_enemy_and_matches_hero_schema(self):
        run = create_run()
        self.assertTrue(Hero().validate_dungeon_data(run))
        encounter = Encounter.from_dict(run['current_encounter'])
        self.assertEqual(encounter.floor, run['current_floor'])
        self.assertEqual(encounter.battle_tier, BattleTier.ENEMY)
        self.assertEqual(run['phase'], 'encounter')
        self.assertIsNone(run['path_left'])
        self.assertIsNone(run['path_right'])

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
        self.assertEqual(len(options), 6)
        self.assertEqual(len(set(options)), 6)
