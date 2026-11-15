"""Percentage resistance behavior and legacy wire compatibility."""
from dataclasses import replace
from unittest.mock import patch

from unittest import TestCase
from . import test_elemental
from .engine import advance, create_battle, snapshot_from_json, snapshot_to_json, state_from_json, state_to_json


class StatusResistanceTests(TestCase):
    setup_battle = test_elemental.ElementalTests.setup_battle
    def with_resistance(self, element, values, **kwargs):
        snapshot, state = self.setup_battle(element, **kwargs)
        hero, target, *others = snapshot.combatants
        snapshot = replace(snapshot, combatants=(hero, replace(target, status_resistances=values), *others))
        return snapshot, state

    def test_percentage_boundaries_do_not_reduce_initial_damage(self):
        for percent, roll, blocked in ((0, 0, False), (30, 2999, True), (30, 3000, False), (100, 9999, True)):
            with self.subTest(percent=percent, roll=roll):
                snapshot, state = self.with_resistance('fire', {'burning': percent})
                # Accuracy, critical, effect trigger, then independent resistance.
                with patch('battle.engine.random_integer', side_effect=[0, 9999, 0, roll]) as rng:
                    result = advance(snapshot, state, 1000)
                target = result.state.combatants['enemy:0']
                self.assertEqual(target.health, 950)
                self.assertEqual('burning' not in target.statuses, blocked)
                self.assertEqual(rng.call_count, 4 if 0 < percent < 100 else 3)

    def test_resisted_frozen_refreshes_chilled(self):
        snapshot, state = self.with_resistance('ice', {'frozen': 100})
        with patch('battle.engine.random_integer', return_value=0):
            first = advance(snapshot, state, 1000)
            second = advance(snapshot, first.state, 2000)
        statuses = second.state.combatants['enemy:0'].statuses
        self.assertEqual(set(statuses), {'chilled'})
        self.assertEqual(statuses['chilled'].expires_at_ms, 5000)

    def test_resisted_chilled_prevents_upgrade(self):
        snapshot, state = self.with_resistance('ice', {'chilled': 100})
        with patch('battle.engine.random_integer', return_value=0):
            result = advance(snapshot, state, 2000)
        self.assertFalse(result.state.combatants['enemy:0'].statuses)

    def test_primary_lightning_resistance_blocks_chain(self):
        snapshot, state = self.with_resistance('lightning', {'static_charge': 100}, enemies=2)
        with patch('battle.engine.random_integer', return_value=0):
            result = advance(snapshot, state, 1000)
        self.assertEqual(result.state.combatants['enemy:1'].health, 1000)

    def test_percentage_replay_and_resumed_checkpoint(self):
        snapshot, state = self.with_resistance('fire', {'burning': 30})
        encoded = snapshot_to_json(snapshot)
        self.assertNotIn('status_immunities', encoded)
        self.assertEqual(snapshot_from_json(encoded), snapshot)
        whole = advance(snapshot, state, 8000)
        part = advance(snapshot, state, 3000)
        resumed = advance(snapshot, state_from_json(snapshot, state_to_json(snapshot, part.state)), 8000)
        self.assertEqual(whole.state, resumed.state)
        self.assertEqual(whole.events, part.events + resumed.events)

    def test_elemental_v1_retains_immunity_wire_and_rng(self):
        snapshot, _ = self.setup_battle('fire')
        hero, target = snapshot.combatants
        snapshot = replace(snapshot, rules_version='elemental-v1', combatants=(hero, replace(target, status_immunities=('burn',))))
        encoded = snapshot_to_json(snapshot)
        self.assertNotIn('status_resistances', encoded)
        self.assertEqual(snapshot_from_json(encoded), snapshot)
        state = create_battle(snapshot)
        state.combatants['enemy:0'].next_attack_at_ms = 10000
        with patch('battle.engine.random_integer', side_effect=[0, 9999, 0]) as rng:
            result = advance(snapshot, state, 1000)
        self.assertEqual(rng.call_count, 3)
        self.assertFalse(result.state.combatants['enemy:0'].statuses)

    def test_old_wire_formats_round_trip_unchanged(self):
        from .test_engine import fixture
        for version in ('melee-v1', 'ranged-v1', 'magic-v1', 'elemental-v1'):
            snapshot = replace(fixture(), rules_version=version)
            encoded = snapshot_to_json(snapshot)
            self.assertEqual(snapshot_to_json(snapshot_from_json(encoded)), encoded)
            state = create_battle(snapshot)
            self.assertEqual(state_from_json(snapshot, state_to_json(snapshot, state)), state)

    def test_snapshot_rejects_invalid_percentages(self):
        for values in ({'burning': True}, {'burning': -1}, {'burning': 101}, {'burning': 1.5}):
            snapshot, _ = self.with_resistance('fire', values)
            with self.assertRaises(ValueError):
                create_battle(snapshot)
