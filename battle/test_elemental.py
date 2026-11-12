from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

from .engine import (advance, create_battle, state_from_json, state_to_json,
                     snapshot_from_json, snapshot_to_json, StatusInstance)
from .test_engine import fixture


class ElementalTests(TestCase):
    def setup_battle(self, element, *, enemies=1, boss=False, immunity=(), resistance=10000):
        snapshot = fixture(adjacent=True, enemies=enemies, policy='hold')
        hero, *targets = snapshot.combatants
        hero = replace(hero, damage_kind='magical', projectile_element=element,
                       stats=replace(hero.stats, magic=50), attack_range_max=8)
        targets = [replace(t, initial_health=1000, stats=replace(t.stats, max_health=1000, attack=0),
                           initial_movement_policy='hold', status_immunities=immunity,
                           elemental_resistances_bp={element: resistance}) for t in targets]
        snapshot = replace(snapshot, combatants=(hero, *targets), battle_tier='boss' if boss else 'enemy')
        state = create_battle(snapshot)
        for target in targets:
            state.combatants[target.combatant_id].next_attack_at_ms = 10000
        return snapshot, state

    def run_hit(self, element, **kwargs):
        snapshot, state = self.setup_battle(element, **kwargs)
        with patch('battle.engine.random_integer', return_value=0):
            result = advance(snapshot, state, 1000)
        return snapshot, result

    def test_all_elements_proc_without_mana_cost(self):
        for element, event in [('fire', 'status_applied'), ('ice', 'status_applied'),
                               ('lightning', 'damage'), ('earth', 'stagger'),
                               ('wind', 'move'), ('dark', 'status_applied')]:
            with self.subTest(element=element):
                snapshot, result = self.run_hit(element, enemies=2 if element == 'lightning' else 1)
                self.assertTrue(any(e.event_type == event for e in result.events))
                self.assertEqual(result.state.combatants['hero'].mana, 50)
        snapshot, state = self.setup_battle('holy')
        state.combatants['hero'].health = 99
        with patch('battle.engine.random_integer', return_value=0):
            result = advance(snapshot, state, 1000)
        self.assertEqual(result.state.combatants['hero'].health, 100)

    def test_resistance_and_failed_proc(self):
        _, result = self.run_hit('fire', resistance=0)
        target = result.state.combatants['enemy:0']
        self.assertEqual(target.health, 1000)
        self.assertFalse(target.statuses)
        snapshot, state = self.setup_battle('fire')
        with patch('battle.engine.random_integer', side_effect=[0, 9999, 9999]):
            result = advance(snapshot, state, 1000)
        self.assertEqual(result.state.combatants['enemy:0'].health, 950)
        self.assertFalse(result.state.combatants['enemy:0'].statuses)

    def test_burn_four_ticks_and_replay(self):
        snapshot, result = self.run_hit('fire')
        state = result.state
        state.combatants['hero'].next_attack_at_ms = 10000
        restored = state_from_json(snapshot, state_to_json(snapshot, state))
        one = advance(snapshot, state, 5000)
        first = advance(snapshot, restored, 2500)
        second = advance(snapshot, state_from_json(snapshot, state_to_json(snapshot, first.state)), 5000)
        self.assertEqual(one.state, second.state)
        self.assertEqual(one.events, first.events + second.events)
        ticks = [e for e in one.events if e.payload.get('effect') == 'burning']
        self.assertEqual([e.simulation_time_ms for e in ticks], [2000, 3000, 4000, 5000])
        self.assertEqual([e.payload['applied'] for e in ticks], [10]*4)
        self.assertFalse(one.state.combatants['enemy:0'].statuses)

    def test_ice_freeze_and_boss(self):
        for boss in (False, True):
            snapshot, result = self.run_hit('ice', boss=boss)
            with patch('battle.engine.random_integer', return_value=0):
                result = advance(snapshot, result.state, 2000)
            statuses = result.state.combatants['enemy:0'].statuses
            self.assertEqual(set(statuses), {'chilled' if boss else 'frozen'})

    def test_immunity_and_refresh(self):
        _, result = self.run_hit('fire', immunity=('burn',))
        self.assertFalse(result.state.combatants['enemy:0'].statuses)
        snapshot, result = self.run_hit('fire')
        with patch('battle.engine.random_integer', return_value=0):
            result = advance(snapshot, result.state, 2000)
        statuses = result.state.combatants['enemy:0'].statuses
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses['burning'].expires_at_ms, 6000)

    def test_miss_never_procs(self):
        snapshot, state = self.setup_battle('fire')
        hero, *targets = snapshot.combatants
        snapshot = replace(snapshot, combatants=(replace(hero, stats=replace(hero.stats, accuracy=5)), *targets))
        with patch('battle.engine.random_integer', return_value=9999) as rng:
            result = advance(snapshot, state, 1000)
        self.assertEqual(rng.call_count, 1)
        self.assertEqual(result.state.combatants['enemy:0'].health, 1000)
        self.assertFalse(result.state.combatants['enemy:0'].statuses)

    def test_dead_target_cancels_burn(self):
        snapshot, result = self.run_hit('fire')
        target = result.state.combatants['enemy:0']
        target.health = 1
        result.state.combatants['hero'].next_attack_at_ms = 10000
        result = advance(snapshot, result.state, 5000)
        self.assertEqual(result.state.phase, 'finished')
        self.assertFalse(result.state.combatants['enemy:0'].statuses)
        self.assertEqual(result.state.simulation_time_ms, 2000)

    def test_freeze_expires_and_attacks_continue(self):
        snapshot, result = self.run_hit('ice')
        with patch('battle.engine.random_integer', return_value=0):
            result = advance(snapshot, result.state, 2000)
        result.state.combatants['hero'].next_attack_at_ms = 10000
        result.state.combatants['enemy:0'].next_attack_at_ms = 2500
        with patch('battle.engine.random_integer', return_value=0):
            result = advance(snapshot, result.state, 3500)
        self.assertTrue(any(e.event_type == 'attack' and e.actor_id == 'enemy:0' for e in result.events))
        self.assertFalse(result.state.combatants['enemy:0'].statuses)

    def test_chain_single_secondary_no_recursion(self):
        _, result = self.run_hit('lightning', enemies=3)
        chain = [e for e in result.events if e.payload.get('effect') == 'static_charge']
        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0].target_id, 'enemy:1')
        self.assertEqual(chain[0].payload['applied'], 18)

    def test_static_charge_immunity_protects_secondary_recipient(self):
        for enemies in (2, 3):
            with self.subTest(enemies=enemies):
                snapshot, state = self.setup_battle('lightning', enemies=enemies)
                hero, primary, secondary, *others = snapshot.combatants
                snapshot = replace(snapshot, combatants=(hero, primary,
                    replace(secondary, status_immunities=('static_charge',)), *others))
                with patch('battle.engine.random_integer', return_value=0):
                    result = advance(snapshot, state, 1000)
                self.assertLess(result.state.combatants['enemy:0'].health, 1000)
                self.assertEqual(result.state.combatants['enemy:1'].health, 1000)
                self.assertFalse(any(e.payload.get('effect') == 'static_charge'
                                     for e in result.events))
                if enemies == 3:
                    self.assertEqual(result.state.combatants['enemy:2'].health, 1000)

    def test_stagger_cap_and_boss_adjustment(self):
        for boss, expected in ((False, 1000), (True, 800)):
            snapshot, state = self.setup_battle('earth', boss=boss)
            with patch('battle.engine.random_integer', return_value=0):
                result = advance(snapshot, state, 4000)
            self.assertEqual(result.state.combatants['enemy:0'].next_attack_at_ms, 10000 + expected)

    def test_gust_blocked_and_boss_immune(self):
        for enemies, boss in ((2, False), (1, True)):
            _, result = self.run_hit('wind', enemies=enemies, boss=boss)
            self.assertEqual(result.state.combatants['enemy:0'].lane, 1)

    def test_withering_reduces_power_without_stacking(self):
        snapshot, result = self.run_hit('dark')
        with patch('battle.engine.random_integer', return_value=0):
            result = advance(snapshot, result.state, 2000)
        self.assertEqual(result.state.combatants['enemy:0'].statuses['withering'].potency, 15)
        _, result = self.run_hit('dark', boss=True)
        self.assertEqual(result.state.combatants['enemy:0'].statuses['withering'].potency, 8)

    def test_every_element_resumes_identically(self):
        for element in ('fire', 'ice', 'lightning', 'earth', 'wind', 'holy', 'dark'):
            with self.subTest(element=element):
                snapshot, state = self.setup_battle(element, enemies=3)
                with patch('battle.engine.random_integer', return_value=0):
                    whole = advance(snapshot, state, 6000)
                    first = advance(snapshot, state, 1700)
                    restored = state_from_json(snapshot, state_to_json(snapshot, first.state))
                    rest = advance(snapshot, restored, 6000)
                self.assertEqual(whole.state, rest.state)
                self.assertEqual(whole.events, first.events + rest.events)

    def test_chill_delays_movement(self):
        snapshot, state = self.setup_battle('ice')
        target = state.combatants['enemy:0']
        target.movement_policy = 'approach'
        target.next_movement_at_ms = 1500
        # Move the hero away so that the enemy would normally advance at 1500.
        state.combatants['hero'].lane = 5
        with patch('battle.engine.random_integer', return_value=0):
            result = advance(snapshot, state, 1500)
        self.assertEqual(result.state.combatants['enemy:0'].lane, 1)
        self.assertEqual(result.state.combatants['enemy:0'].next_movement_at_ms, 1834)

    def test_chill_expiry_restores_remaining_movement_delay(self):
        snapshot, state = self.setup_battle('ice')
        state.combatants['enemy:0'].movement_policy = 'approach'
        state.combatants['enemy:0'].next_movement_at_ms = 1500
        state.combatants['hero'].lane = 8
        with patch('battle.engine.random_integer', return_value=0):
            chilled = advance(snapshot, state, 1000)
        # Prevent reapplications so the original Chill expires at 4000 ms.
        chilled.state.combatants['hero'].next_attack_at_ms = 10000
        before_expiry = advance(snapshot, chilled.state, 3999)
        target = before_expiry.state.combatants['enemy:0']
        self.assertEqual(target.next_movement_at_ms, 5168)
        self.assertEqual([e.simulation_time_ms for e in before_expiry.events
                          if e.event_type == 'move'], [1834, 3501])
        restored = state_from_json(snapshot, state_to_json(snapshot, before_expiry.state))
        expired = advance(snapshot, restored, 4000)
        target = expired.state.combatants['enemy:0']
        self.assertNotIn('chilled', target.statuses)
        self.assertEqual(target.next_movement_at_ms, 4701)
        resumed = advance(snapshot, expired.state, 5701)
        self.assertEqual([e.simulation_time_ms for e in resumed.events
                          if e.event_type == 'move'], [4701, 5701])
        whole = advance(snapshot, chilled.state, 5701)
        self.assertEqual(whole.state, resumed.state)
        self.assertEqual(whole.events, before_expiry.events + expired.events + resumed.events)

    def test_chill_expiry_at_movement_timestamp_keeps_action_due(self):
        snapshot, state = self.setup_battle('ice')
        target = state.combatants['enemy:0']
        target.movement_policy = 'approach'
        target.statuses['chilled'] = StatusInstance('chilled', 'hero', 1500)
        target.next_movement_at_ms = 1500
        state.combatants['hero'].lane = 8
        state.combatants['hero'].next_attack_at_ms = 10000
        result = advance(snapshot, state, 1500)
        self.assertEqual(result.state.combatants['enemy:0'].lane, 2)
        self.assertEqual(result.state.combatants['enemy:0'].next_movement_at_ms, 2500)

    def test_withering_changes_actual_attack_damage(self):
        snapshot, state = self.setup_battle('dark')
        hero, target = snapshot.combatants
        snapshot = replace(snapshot, combatants=(hero, replace(target, stats=replace(target.stats, attack=100))))
        state.combatants['enemy:0'].next_attack_at_ms = 1500
        with patch('battle.engine.random_integer', return_value=0):
            result = advance(snapshot, state, 1500)
        damage = next(e for e in result.events if e.event_type == 'damage' and e.actor_id == 'enemy:0')
        self.assertEqual(damage.payload['damage'], 85)

    def test_legacy_magic_has_no_effects_or_additional_rng(self):
        snapshot, state = self.setup_battle('fire')
        snapshot = replace(snapshot, rules_version='magic-v1', combatants=tuple(
            replace(c, elemental_resistances_bp={}) for c in snapshot.combatants))
        snapshot = snapshot_from_json(snapshot_to_json(snapshot))
        state = state_from_json(snapshot, state_to_json(snapshot, state))
        with patch('battle.engine.random_integer', return_value=0) as rng:
            result = advance(snapshot, state, 1000)
        self.assertEqual(rng.call_count, 2)
        self.assertFalse(result.state.combatants['enemy:0'].statuses)
