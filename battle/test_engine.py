"""Behavioral tests for the standalone melee simulation."""
from copy import deepcopy
from dataclasses import replace
import json
from unittest import TestCase
from unittest.mock import patch

from .engine import (
    AdvanceResult, BattleCommandInput, BattleRules, BattleSnapshot,
    CombatStats, CombatantSnapshot, LootEntry, RewardSnapshot, RngState,
    RULES_VERSION, SimulationLimitReached, advance, attack_interval_ms, create_battle,
    random_integer, snapshot_from_json, snapshot_to_json, state_from_json,
    state_to_json, validate_state,
)


def fixture(*, adjacent=False, enemies=1, hero_stats=None, enemy_stats=None,
            policy='approach', limit=600000, loot=()):
    stats = CombatStats(100, 50, 10, 0, 0, 0, 20, 100, 0, 0, 15000)
    hero = CombatantSnapshot('hero', 'hero', 'hero', 1, 'Hero', hero_stats or stats,
        1, 1, (hero_stats or stats).max_health, 50, 0, policy, None)
    opponents = tuple(CombatantSnapshot(f'enemy:{i}', 'enemy', 'monster', i+1,
        'Enemy', enemy_stats or stats, 1, 1, (enemy_stats or stats).max_health,
        50, i+1 if adjacent else 8-i, 'approach', RewardSnapshot(7, loot))
        for i in range(enemies))
    return BattleSnapshot(1, RULES_VERSION, 'sha256-counter-v1', 'battle', 'encounter',
        'goblin_ambush', 1, 'enemy', BattleRules(9, 1000, limit, 334, 2000, 20),
        (hero,) + opponents, 'seed')


class CombatTests(TestCase):
    def test_initialization_and_snapshot_round_trip(self):
        snapshot = fixture()
        self.assertEqual(snapshot_from_json(snapshot_to_json(snapshot)), snapshot)
        state = create_battle(snapshot)
        self.assertEqual(state.combatants['hero'].next_attack_at_ms, 1000)
        self.assertEqual(state.rng, RngState('seed', 0))
        self.assertEqual(state_from_json(snapshot, state_to_json(snapshot, state)), state)

    def test_advance_does_not_mutate_inputs(self):
        snapshot = fixture(adjacent=True)
        state = create_battle(snapshot)
        before = deepcopy((snapshot, state))
        advance(snapshot, state, 1000)
        self.assertEqual((snapshot, state), before)

    def test_schema_and_shape_validation(self):
        snapshot = fixture()
        for invalid in (replace(snapshot, schema_version=2),
                        replace(snapshot, rules_version='unknown'),
                        replace(snapshot, rng_version='unknown'),
                        replace(snapshot, combatants=list(snapshot.combatants)),
                        replace(snapshot, combatants=(snapshot.combatants[0],)*2)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                create_battle(invalid)
        data = json.loads(snapshot_to_json(snapshot))
        data['surprise'] = 1
        with self.assertRaises(ValueError):
            snapshot_from_json(json.dumps(data))
        data.pop('surprise')
        data['floor'] = True
        with self.assertRaises(ValueError):
            snapshot_from_json(json.dumps(data))

    def test_checkpoint_invariants(self):
        snapshot = fixture()
        base = create_battle(snapshot)
        for field, value in [('health', 101), ('lane', 9), ('next_attack_at_ms', 0),
                             ('movement_policy', 'retreat'), ('current_target_id', 'hero')]:
            state = deepcopy(base)
            setattr(state.combatants['hero'], field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_state(snapshot, state)
        for field, value in [('battle_id', 'other'), ('simulation_time_ms', -1)]:
            with self.assertRaises(ValueError):
                validate_state(snapshot, replace(base, **{field: value}))

    def test_invalid_policies_and_ranges_rejected(self):
        snapshot = fixture()
        for actor in (replace(snapshot.combatants[0], initial_movement_policy='retreat'),
                      replace(snapshot.combatants[0], attack_range_max=9),
                      replace(snapshot.combatants[0], attack_range_min=0),
                      replace(snapshot.combatants[0], attack_range_min=2)):
            with self.assertRaises(ValueError):
                create_battle(replace(snapshot, combatants=(actor, snapshot.combatants[1])))

    def test_ranged_hero_and_enemy_attack_at_distance_and_stop(self):
        base = fixture()
        for ranged_id in ('hero', 'enemy:0'):
            with self.subTest(ranged_id=ranged_id):
                actors = tuple(replace(c, attack_range_max=4) if c.combatant_id == ranged_id
                               else replace(c, initial_movement_policy='hold') for c in base.combatants)
                snapshot = replace(base, combatants=actors)
                result = advance(snapshot, create_battle(snapshot), 5000)
                self.assertEqual(abs(result.state.combatants['hero'].lane - result.state.combatants['enemy:0'].lane), 4)
                attacks = [e for e in result.events if e.event_type == 'attack']
                self.assertTrue(attacks)
                self.assertTrue(all(e.actor_id == ranged_id and e.payload['ranged'] for e in attacks))

    def test_ranged_can_select_and_hit_enemy_behind_front_line(self):
        base = fixture(enemies=2, policy='hold')
        actors = tuple(replace(c, attack_range_max=8) if c.team == 'hero'
                       else replace(c, initial_movement_policy='hold') for c in base.combatants)
        snapshot = replace(base, combatants=actors)
        command = BattleCommandInput(1, 0, 'select_target', {'target_id': 'enemy:0'})
        result = advance(snapshot, create_battle(snapshot), 1000, (command,))
        self.assertTrue(result.command_results[0].accepted)
        self.assertEqual(result.state.combatants['enemy:0'].health, 90)
        self.assertEqual(result.state.combatants['enemy:1'].health, 100)

    def test_ranged_checkpoint_resume_is_deterministic(self):
        base = fixture()
        snapshot = replace(base, combatants=(replace(base.combatants[0], attack_range_max=4), base.combatants[1]))
        first = advance(snapshot, create_battle(snapshot), 2500)
        restored = state_from_json(snapshot, state_to_json(snapshot, first.state))
        second = advance(snapshot, restored, 6000)
        full = advance(snapshot, create_battle(snapshot), 6000)
        self.assertEqual(second.state, full.state)
        self.assertEqual(first.events + second.events, full.events)

    def test_legacy_melee_snapshots_remain_supported(self):
        snapshot = replace(fixture(), rules_version='melee-v1')
        self.assertEqual(snapshot_from_json(snapshot_to_json(snapshot)), snapshot)
        self.assertTrue(advance(snapshot, create_battle(snapshot), 5000).events)
        with self.assertRaises(ValueError):
            create_battle(replace(snapshot, combatants=(replace(snapshot.combatants[0], attack_range_max=4), snapshot.combatants[1])))

    def test_approach_stops_at_melee(self):
        snapshot = fixture()
        result = advance(snapshot, create_battle(snapshot), 5000)
        hero, enemy = result.state.combatants.values()
        self.assertEqual(abs(hero.lane-enemy.lane), 1)
        moves = [e for e in result.events if e.event_type == 'move' and e.simulation_time_ms > 4000]
        self.assertEqual(moves, [])

    def test_adjacent_never_moves(self):
        snapshot = fixture(adjacent=True)
        result = advance(snapshot, create_battle(snapshot), 2000)
        self.assertFalse(any(e.event_type == 'move' for e in result.events))

    def test_hold_and_boundaries(self):
        snapshot = fixture(policy='hold')
        result = advance(snapshot, create_battle(snapshot), 4000)
        self.assertEqual(result.state.combatants['hero'].lane, 0)
        self.assertTrue(all(0 <= c.lane <= 8 for c in result.state.combatants.values()))

    def test_blocked_manual_target_rejected(self):
        snapshot = fixture(enemies=2)
        cmd = BattleCommandInput(1, 0, 'select_target', {'target_id': 'enemy:0'})
        result = advance(snapshot, create_battle(snapshot), 0, (cmd,))
        self.assertFalse(result.command_results[0].accepted)
        self.assertEqual(result.state.combatants['hero'].current_target_id, 'enemy:1')

    def test_manual_target_outside_range_accepted(self):
        snapshot = fixture()
        cmd = BattleCommandInput(1, 0, 'select_target', {'target_id': 'enemy:0'})
        result = advance(snapshot, create_battle(snapshot), 0, (cmd,))
        self.assertTrue(result.command_results[0].accepted)
        self.assertEqual(result.state.combatants['hero'].selected_target_id, 'enemy:0')

    def test_spd_attack_cadence_and_movement_independence(self):
        snapshot = fixture()
        stats = snapshot.combatants[0].stats
        self.assertEqual([attack_interval_ms(replace(stats, speed=s), snapshot.rules)
                          for s in (0, 10, 20, 40, 80, 999)],
                         [2000, 1334, 1000, 667, 400, 334])
        fast = replace(snapshot.combatants[0], stats=replace(stats, speed=80))
        snapshot = replace(snapshot, combatants=(fast, snapshot.combatants[1]))
        result = advance(snapshot, create_battle(snapshot), 1000)
        self.assertEqual(result.state.combatants['hero'].lane, 1)
        self.assertEqual(result.state.combatants['hero'].next_attack_at_ms, 1200)
        self.assertFalse(any(e.event_type == 'attack' for e in result.events))

    def test_command_before_movement_before_attack(self):
        snapshot = fixture()
        enemy = replace(snapshot.combatants[1], initial_lane=2, initial_movement_policy='hold')
        snapshot = replace(snapshot, combatants=(snapshot.combatants[0], enemy))
        result = advance(snapshot, create_battle(snapshot), 1000)
        kinds = [e.event_type for e in result.events]
        self.assertLess(kinds.index('move'), kinds.index('attack'))
        cmd = BattleCommandInput(1, 1000, 'set_movement_policy', {'policy': 'hold'})
        held = advance(snapshot, create_battle(snapshot), 1000, (cmd,))
        self.assertFalse(any(e.event_type in ('move', 'attack') for e in held.events))

    def test_blocked_opportunities_do_not_stack(self):
        snapshot = fixture(policy='hold')
        state = create_battle(snapshot)
        state.combatants['enemy:0'].movement_policy = 'hold'
        result = advance(snapshot, state, 5500)
        self.assertEqual(result.state.combatants['hero'].next_attack_at_ms, 6000)
        self.assertEqual(result.state.rng.counter, 0)

    def test_damage_rounding_and_critical(self):
        base = fixture(adjacent=True)
        hero = replace(base.combatants[0].stats, attack=10, defense=0, critical_chance=100)
        enemy = replace(hero, defense=3, critical_chance=0)
        snapshot = fixture(adjacent=True, hero_stats=hero, enemy_stats=enemy)
        result = advance(snapshot, create_battle(snapshot), 1000)
        damage = next(e for e in result.events if e.event_type == 'damage' and e.actor_id == 'hero')
        self.assertEqual(damage.payload['damage'], 13)  # 8.5 * 1.5 rounds half up
        self.assertTrue(any(e.event_type == 'critical' for e in result.events))

    def test_hit_floor_and_critical_clamp(self):
        base = fixture(adjacent=True)
        hero = replace(base.combatants[0].stats, accuracy=0, critical_chance=200)
        snapshot = fixture(adjacent=True, hero_stats=hero)
        # Enemy draws first, then hero hit roll at the 5% boundary.
        with patch('battle.engine.random_integer', side_effect=[0, 9999, 500]):
            result = advance(snapshot, create_battle(snapshot), 1000)
        self.assertTrue(any(e.event_type == 'miss' and e.actor_id == 'hero' for e in result.events))
        with patch('battle.engine.random_integer', side_effect=[0, 9999, 499, 9999]):
            result = advance(snapshot, create_battle(snapshot), 1000)
        self.assertTrue(any(e.event_type == 'critical' and e.actor_id == 'hero' for e in result.events))

    def test_immediate_death_prevents_later_attack(self):
        base = fixture(adjacent=True)
        stats = replace(base.combatants[1].stats, attack=999)
        snapshot = fixture(adjacent=True, enemy_stats=stats)
        result = advance(snapshot, create_battle(snapshot), 1000)
        self.assertEqual(result.state.outcome.result, 'defeat')
        self.assertFalse(any(e.event_type == 'attack' and e.actor_id == 'hero' for e in result.events))
        self.assertEqual(result.state.outcome.experience, 0)

    def test_multi_enemy_victory_target_replacement_and_rewards_once(self):
        base = fixture()
        hero = replace(base.combatants[0].stats, attack=999, max_health=10000)
        loot = (LootEntry(1, 10000, 2, 2), LootEntry(2, 0, 1, 1))
        snapshot = fixture(enemies=3, hero_stats=hero, loot=loot)
        cmd = BattleCommandInput(1, 0, 'select_target', {'target_id': 'enemy:2'})
        result = advance(snapshot, create_battle(snapshot), 20000, (cmd,))
        self.assertEqual(result.state.outcome.result, 'victory')
        self.assertEqual(result.state.outcome.experience, 21)
        self.assertEqual(len(result.state.outcome.loot), 3)
        self.assertTrue(all(d.item_id == 1 and d.quantity == 2 for d in result.state.outcome.loot))
        self.assertEqual(sum(e.event_type == 'defeat' for e in result.events), 3)
        self.assertIsNone(result.state.combatants['hero'].selected_target_id)
        again = advance(snapshot, result.state, 30000)
        self.assertEqual(again.state, result.state)
        self.assertEqual(again.events, ())

    def test_checkpointed_matches_continuous_including_events(self):
        snapshot = fixture()
        original = create_battle(snapshot)
        full = advance(snapshot, original, 6000)
        first = advance(snapshot, original, 1350)
        restored = state_from_json(snapshot, state_to_json(snapshot, first.state))
        second = advance(snapshot, restored, 6000)
        self.assertEqual(second.state, full.state)
        self.assertEqual(first.events + second.events, full.events)

    def test_command_rejection_deduplication_and_order(self):
        snapshot = fixture()
        commands = (BattleCommandInput(1, 0, 'set_movement_policy', {'policy': 'retreat'}),
                    BattleCommandInput(2, 0, 'unsupported', {}),
                    BattleCommandInput(3, 0, 'set_movement_policy', {'policy': 'hold'}))
        result = advance(snapshot, create_battle(snapshot), 0, commands)
        self.assertEqual([r.accepted for r in result.command_results], [False, False, True])
        replay = advance(snapshot, result.state, 0, commands)
        self.assertEqual(replay.command_results, ())
        self.assertEqual(replay.state, result.state)
        for invalid in ((commands[2], commands[0]),
                        (BattleCommandInput(1, 2000, 'select_target', {}),), ({},)):
            with self.assertRaises(ValueError):
                advance(snapshot, create_battle(snapshot), 1000, invalid)

    def test_finished_commands_rejected(self):
        base = fixture(adjacent=True)
        snapshot = fixture(adjacent=True, enemy_stats=replace(base.combatants[1].stats, attack=999))
        cmd = BattleCommandInput(1, 1500, 'set_movement_policy', {'policy': 'hold'})
        result = advance(snapshot, create_battle(snapshot), 2000, (cmd,))
        self.assertEqual(result.command_results[0].reason, 'battle_finished')
        self.assertEqual(result.state.simulation_time_ms, 1000)

    def test_limit_carries_valid_checkpoint_and_events(self):
        snapshot = fixture(limit=1500)
        state = create_battle(snapshot)
        with self.assertRaises(SimulationLimitReached) as error:
            advance(snapshot, state, 5000)
        result = error.exception.result
        self.assertIsInstance(result, AdvanceResult)
        self.assertEqual(result.state.simulation_time_ms, 1500)
        self.assertTrue(result.events)
        self.assertIsNone(result.state.outcome)
        validate_state(snapshot, result.state)
        with self.assertRaises(ValueError):
            advance(snapshot, result.state, 1499)

    def test_rng_determinism_bounds_and_rejection_sampling(self):
        a, b = RngState('seed', 0), RngState('seed', 0)
        draws = [random_integer(a, 2, 4) for _ in range(100)]
        self.assertEqual(draws, [random_integer(b, 2, 4) for _ in range(100)])
        self.assertEqual(set(draws), {2, 3, 4})
        with patch('battle.engine.hashlib.sha256') as digest:
            digest.return_value.digest.side_effect = [b'\xff'*32, b'\x00'*32]
            rng = RngState('seed', 0)
            self.assertEqual(random_integer(rng, 0, 2), 0)
            self.assertEqual(rng.counter, 2)

    def test_terminal_checkpoint_round_trip(self):
        base = fixture(adjacent=True)
        snapshot = fixture(adjacent=True, enemy_stats=replace(base.combatants[1].stats, attack=999))
        state = advance(snapshot, create_battle(snapshot), 2000).state
        self.assertEqual(state_from_json(snapshot, state_to_json(snapshot, state)), state)

    def test_negative_speed_uses_base_interval(self):
        snapshot = fixture()
        hero = replace(snapshot.combatants[0], stats=replace(snapshot.combatants[0].stats, speed=-20))
        snapshot = replace(snapshot, combatants=(hero, snapshot.combatants[1]))
        self.assertEqual(create_battle(snapshot).combatants['hero'].next_attack_at_ms, 2000)

    def test_commands_across_checkpoints_match_continuous_run(self):
        snapshot = fixture()
        commands = (BattleCommandInput(1, 1000, 'set_movement_policy', {'policy': 'hold'}),
                    BattleCommandInput(2, 2500, 'set_movement_policy', {'policy': 'approach'}))
        full = advance(snapshot, create_battle(snapshot), 5000, commands)
        first = advance(snapshot, create_battle(snapshot), 2000, commands[:1])
        second = advance(snapshot, first.state, 5000, commands)
        self.assertEqual(second.state, full.state)
        self.assertEqual(first.events + second.events, full.events)
        self.assertEqual(first.command_results + second.command_results, full.command_results)

    def test_high_accuracy_and_minimum_damage(self):
        base = fixture(adjacent=True)
        hero = replace(base.combatants[0].stats, accuracy=999, attack=0)
        enemy = replace(base.combatants[1].stats, defense=999)
        snapshot = fixture(adjacent=True, hero_stats=hero, enemy_stats=enemy)
        with patch('battle.engine.random_integer', return_value=9999):
            result = advance(snapshot, create_battle(snapshot), 1000)
        event = next(e for e in result.events if e.event_type == 'damage' and e.actor_id == 'hero')
        self.assertEqual(event.payload['damage'], 1)

    def test_occupied_lanes_never_overlap_during_advance(self):
        snapshot = fixture(enemies=3)
        state = create_battle(snapshot)
        for timestamp in range(500, 6500, 500):
            state = advance(snapshot, state, timestamp).state
            lanes = [c.lane for c in state.combatants.values() if c.health]
            self.assertEqual(len(lanes), len(set(lanes)))

    def test_invalid_loot_and_terminal_outcome_rejected(self):
        snapshot = fixture(loot=(LootEntry(1, 10001, 1, 1),))
        with self.assertRaises(ValueError):
            create_battle(snapshot)
        base = fixture()
        hero = replace(base.combatants[0].stats, attack=999, max_health=1000)
        snapshot = fixture(adjacent=True, hero_stats=hero, loot=(LootEntry(1, 10000, 1, 1),))
        state = advance(snapshot, create_battle(snapshot), 1000).state
        state.outcome.loot *= 2
        with self.assertRaises(ValueError):
            validate_state(snapshot, state)
