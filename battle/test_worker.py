"""Integration tests for the standalone worker and transactional adapter."""
from dataclasses import replace
from datetime import timedelta
import json
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from battle_daemon import BattleDaemon, main
from hero.dungeon import create_run, apply_action
from hero.encounters import Encounter
from hero.models import Hero, HeroClass, Monster, MonsterLoot
from item.models import Item, InventoryItem, Equipment, EquipmentSlot, Weapon, Accessory
from .models import Battle, BattleCommand, BattleWorkerLease, EncounterMonster
from .services import (LeaseLost, acquire_lease, release_lease, discover_battles,
                       process_battle, retry_battle, build_snapshot)
from .engine import create_battle, snapshot_to_json, state_to_json


class WorkerTests(TestCase):
    def setUp(self):
        choice = patch('hero.dungeon.random.choice', return_value='goblin_ambush')
        choice.start()
        self.addCleanup(choice.stop)
        self.hero = Hero.objects.create(name='Fighter', hero_class=HeroClass.objects.create(name='Warrior'),
            attack=1000, max_health=1000, current_health=1000, dungeon_run=create_run(), is_in_combat=True)
        self.monster = Monster.objects.create(name='Goblin', max_health=10, current_health=3,
            attack=1, defense=0, experience_reward=17)
        self.composition = EncounterMonster.objects.create(encounter_definition_key='goblin_ambush', monster=self.monster)
        self.token = 'owner'
        self.assertTrue(acquire_lease(self.token))

    def adopt(self):
        discover_battles(self.token)
        return Battle.objects.get(hero=self.hero)

    def test_discovery_skips_idle_expeditions_before_bounding_candidates(self):
        choices = create_run()
        choices['phase'] = 'choices'
        runs = [choices]
        for key in ('spike_pit', 'forgotten_cache', 'wandering_healer'):
            run = create_run()
            run['current_encounter'] = Encounter.create(key, 1).to_dict()
            runs.append(run)
        Hero.objects.filter(pk=self.hero.pk).update(dungeon_run=runs[0])
        for index, run in enumerate(runs[1:] * 3):
            Hero.objects.create(name=f'Idle {index}', hero_class=self.hero.hero_class,
                                dungeon_run=run, is_in_combat=True)
        fighters = [Hero.objects.create(name=f'Legacy fighter {index}', hero_class=self.hero.hero_class,
                                       dungeon_run=create_run(), is_in_combat=True)
                    for index in range(3)]
        from .services import fence
        with patch('battle.services.fence', wraps=fence) as fencing:
            self.assertEqual(discover_battles(self.token, limit=2), 2)
            self.assertEqual(fencing.call_count, 2)
        self.assertSetEqual(set(Battle.objects.values_list('hero_id', flat=True)),
                            {hero.pk for hero in fighters[:2]})
        self.assertEqual(discover_battles(self.token, limit=2), 1)
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(discover_battles(self.token, limit=2), 0)
        self.assertEqual(len(queries), 1)  # Idle expeditions need only a read, no fencing writes.

    def test_discovery_rejections_consume_candidate_budget(self):
        run = create_run()
        run['current_encounter']['floor'] = 2  # Rejected by transactional revalidation.
        Hero.objects.filter(pk=self.hero.pk).update(dungeon_run=run)
        other = Hero.objects.create(name='Later fighter', hero_class=self.hero.hero_class,
                                   dungeon_run=create_run(), is_in_combat=True)
        from .services import fence
        with patch('battle.services.fence', wraps=fence) as fencing:
            self.assertEqual(discover_battles(self.token, limit=1), 0)
            self.assertEqual(fencing.call_count, 1)
        self.assertFalse(Battle.objects.filter(hero=other).exists())

    def test_discovery_zero_budget_does_no_work(self):
        with self.assertNumQueries(0):
            self.assertEqual(discover_battles(self.token, limit=0), 0)

    def test_discovery_skips_deleted_candidate_and_worker_processes_later_fight(self):
        other = Hero.objects.create(name='Surviving fighter', hero_class=self.hero.hero_class,
                                   dungeon_run=create_run(), is_in_combat=True)
        deleted_id = self.hero.pk
        from .services import fence

        def delete_before_revalidation(token):
            fence(token)
            # Discovery has already materialized its candidate IDs at this point.
            Hero.objects.filter(pk=deleted_id).delete()

        worker = BattleDaemon()
        worker.token = self.token
        with patch('battle.services.fence', side_effect=delete_before_revalidation):
            self.assertEqual(worker.tick(), 1)
        self.assertFalse(Hero.objects.filter(pk=deleted_id).exists())
        self.assertEqual(Battle.objects.get(hero=other).status, 'ACTIVE')

    def fight(self, battle):
        for _ in range(20):
            status = process_battle(battle.pk, self.token, 1000)
            if status != 'ACTIVE':
                return status
        self.fail('Battle did not finish')

    def test_regular_victory_advances_saved_progress_once(self):
        battle = self.adopt()
        self.assertEqual(self.fight(battle), 'FINISHED')
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.dungeon_run['regular_victories'], 1)
        self.assertEqual(process_battle(battle.pk, self.token, 1000), 'FINISHED')
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.dungeon_run['regular_victories'], 1)

    def test_miniboss_victory_unlocks_second_regular_stage(self):
        self.composition.encounter_definition_key = 'ogre_guard'
        self.composition.save()
        run = self.hero.dungeon_run
        run['current_encounter'] = Encounter.create('ogre_guard', 4).to_dict()
        run.update(current_floor=4, regular_victories=3)
        self.hero.dungeon_run = run
        self.hero.save(update_fields=['dungeon_run'])
        battle = self.adopt()
        self.assertEqual(self.fight(battle), 'FINISHED')
        self.hero.refresh_from_db()
        self.assertTrue(self.hero.dungeon_run['miniboss_defeated'])
        self.assertEqual(self.hero.dungeon_run['regular_victories'], 0)

    def test_adoption_setup_and_snapshot_equipment(self):
        equipment = Equipment.objects.create(hero=self.hero)
        weapon = Weapon.objects.create(name='Sword', attack_bonus=12, accuracy_bonus=5)
        ring = Accessory.objects.create(name='Ring', speed_bonus=8)
        EquipmentSlot.objects.create(equipment=equipment, slot='weapon', item=weapon)
        EquipmentSlot.objects.create(equipment=equipment, slot='accessory', item=ring)
        battle = self.adopt()
        discover_battles(self.token)
        self.assertEqual(Battle.objects.count(), 1)
        self.assertEqual(process_battle(battle.pk, self.token, 1000), 'ACTIVE')
        battle.refresh_from_db()
        self.assertEqual(battle.checkpoint['simulation_time_ms'], 0)
        stats = battle.snapshot['combatants'][0]['stats']
        self.assertEqual((stats['attack'], stats['accuracy'], stats['speed']), (1012, 105, 18))
        self.assertEqual(battle.snapshot['combatants'][1]['initial_health'], 10)
        battle.full_clean()

    def test_victory_resources_rewards_and_resolution_once(self):
        item = Item.objects.create(name='Loot')
        MonsterLoot.objects.create(monster=self.monster, item=item, drop_chance=100, min_quantity=2, max_quantity=2)
        battle = self.adopt()
        self.assertEqual(self.fight(battle), 'FINISHED')
        battle.refresh_from_db()
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.experience, 17)
        self.assertEqual(self.hero.dungeon_run['phase'], 'choices')
        self.assertEqual(self.hero.dungeon_run['last_result']['loot'], [
            {'item_id': item.pk, 'name': 'Loot', 'quantity': 2}])
        self.assertTrue(self.hero.is_in_combat)
        self.assertIsNotNone(battle.resolved_at)
        self.assertEqual(InventoryItem.objects.get(inventory=self.hero.inventory, item=item).quantity, 2)
        events = battle.events.count()
        process_battle(battle.pk, self.token, 1000)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.experience, 17)
        self.assertEqual(battle.events.count(), events)
        self.monster.refresh_from_db()
        self.assertEqual(self.monster.current_health, 3)

    def test_defeat_and_boss_end_run(self):
        self.monster.attack = 100000
        self.monster.save()
        battle = self.adopt()
        self.fight(battle)
        self.hero.refresh_from_db()
        battle.refresh_from_db()
        self.assertEqual(battle.outcome, 'DEFEAT')
        self.assertEqual((self.hero.current_health, self.hero.experience, self.hero.dungeon_run), (1, 0, {}))
        self.assertFalse(self.hero.is_in_combat)

    def test_boss_victory(self):
        run = create_run()
        run['current_encounter'] = Encounter.create('dungeon_guardian', 1).to_dict()
        self.hero.dungeon_run = run
        self.hero.save()
        EncounterMonster.objects.create(encounter_definition_key='dungeon_guardian', monster=self.monster)
        self.fight(self.adopt())
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.dungeon_run, {})
        self.assertFalse(self.hero.is_in_combat)
        self.assertEqual(self.hero.experience, 17)

    def test_commands_receipts_invalid_payload_and_order(self):
        battle = self.adopt()
        a = BattleCommand.objects.create(battle=battle, sequence=1, command_type='select_target', payload=None)
        b = BattleCommand.objects.create(battle=battle, sequence=2, command_type='set_movement_policy', payload={'policy': 'hold'})
        c = BattleCommand.objects.create(battle=battle, sequence=3, command_type='select_target', payload={'target_id': 'enemy:0'})
        process_battle(battle.pk, self.token, 0)
        for command in (a, b, c):
            command.refresh_from_db()
        self.assertEqual((a.status, b.status, c.status), ('REJECTED', 'ACCEPTED', 'ACCEPTED'))
        self.assertEqual(b.execute_at_ms, 0)
        battle.refresh_from_db()
        self.assertEqual(battle.checkpoint['combatants']['hero']['movement_policy'], 'hold')
        self.assertEqual(battle.last_processed_command_sequence, 3)

    def test_duplicate_worker_and_expired_token_fenced(self):
        self.assertFalse(acquire_lease('other'))
        battle = self.adopt()
        BattleWorkerLease.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertTrue(acquire_lease('other'))
        with self.assertRaises(LeaseLost):
            process_battle(battle.pk, self.token, 0)
        release_lease(self.token)
        self.assertEqual(BattleWorkerLease.objects.get().owner_token, 'other')

    def test_restart_does_not_catch_up_wall_time(self):
        battle = self.adopt()
        process_battle(battle.pk, self.token, 0)
        process_battle(battle.pk, self.token, 700)
        Battle.objects.filter(pk=battle.pk).update(next_due_at=timezone.now()-timedelta(days=1))
        worker = BattleDaemon()
        worker.token = self.token
        with patch('battle_daemon.time.monotonic', return_value=999999):
            worker.tick()
        battle.refresh_from_db()
        self.assertEqual(battle.checkpoint['simulation_time_ms'], 700)

    def test_missing_configuration_pauses_and_retry_recovers(self):
        self.composition.delete()
        release_lease(self.token)
        worker = BattleDaemon()
        with self.assertLogs('battle_daemon', level='ERROR'):
            worker.run(once=True)
        battle = Battle.objects.get(hero=self.hero)
        self.assertEqual(battle.status, 'PAUSED_ERROR')
        self.assertIn('Configure', battle.error_message)
        self.assertIsNone(battle.checkpoint)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.current_health, 1000)
        EncounterMonster.objects.create(encounter_definition_key='goblin_ambush', monster=self.monster)
        self.assertTrue(acquire_lease(self.token))
        retry_battle(battle.pk, self.token)
        self.assertEqual(process_battle(battle.pk, self.token, 0), 'ACTIVE')

    def test_atomic_rollback_on_event_write_failure(self):
        battle = self.adopt()
        process_battle(battle.pk, self.token, 0)
        before = Battle.objects.get(pk=battle.pk).checkpoint
        with patch('battle.services.BattleEvent.objects.bulk_create', side_effect=RuntimeError('write failure')):
            with self.assertRaises(RuntimeError):
                process_battle(battle.pk, self.token, 1000)
        battle.refresh_from_db()
        self.assertEqual(battle.checkpoint, before)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.current_health, 1000)

    def test_resolution_rollback_no_reward_delivery(self):
        battle = self.adopt()
        process_battle(battle.pk, self.token, 0)
        with patch('battle.services._resolve', side_effect=RuntimeError('resolution failure')):
            with self.assertRaises(RuntimeError):
                for _ in range(20):
                    process_battle(battle.pk, self.token, 1000)
        battle.refresh_from_db()
        self.assertEqual(battle.checkpoint['phase'], 'active')
        self.assertFalse(battle.events.filter(event_type='battle_complete').exists())
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.experience, 0)
        self.assertEqual(self.fight(battle), 'FINISHED')
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.experience, 17)

    def test_stale_encounter_and_external_resource_change_rejected(self):
        battle = self.adopt()
        process_battle(battle.pk, self.token, 0)
        Hero.objects.filter(pk=self.hero.pk).update(current_health=900)
        with self.assertRaisesRegex(RuntimeError, 'resources changed'):
            process_battle(battle.pk, self.token, 1000)
        Hero.objects.filter(pk=self.hero.pk).update(dungeon_run={})
        with self.assertRaisesRegex(RuntimeError, 'no longer'):
            process_battle(battle.pk, self.token, 1000)

    def test_manual_resolve_cannot_bypass_worker(self):
        self.assertEqual(apply_action(self.hero.pk, 'resolve', self.hero.dungeon_revision), 'invalid')

    def test_standalone_shutdown_releases_lease(self):
        release_lease(self.token)
        worker = BattleDaemon()
        with patch.object(worker, 'tick', side_effect=RuntimeError('loop failure')):
            with self.assertRaises(RuntimeError):
                worker.run(once=True)
        self.assertEqual(BattleWorkerLease.objects.get().owner_token, '')

    def test_status_command_does_not_start_worker(self):
        with patch('battle_daemon.setup_django'), patch('battle_daemon.logging.basicConfig'), patch('builtins.print') as output:
            self.assertEqual(main(['status']), 0)
        self.assertTrue(output.called)

    def test_simulation_limit_checkpoint_and_resources_commit(self):
        battle = self.adopt()
        snapshot = build_snapshot(battle, self.hero)
        snapshot = replace(snapshot, rules=replace(snapshot.rules, max_simulation_ms=1000))
        state = create_battle(snapshot)
        battle.snapshot = json.loads(snapshot_to_json(snapshot))
        battle.checkpoint = json.loads(state_to_json(snapshot, state))
        battle.status = 'ACTIVE'
        battle.save()
        self.assertEqual(process_battle(battle.pk, self.token, 1000), 'PAUSED_ERROR')
        battle.refresh_from_db()
        self.assertEqual(battle.error_code, 'simulation_limit')
        self.assertEqual(battle.checkpoint['simulation_time_ms'], 1000)
        self.assertIsNone(battle.resolved_at)
        with self.assertRaises(ValueError):
            retry_battle(battle.pk, self.token)

    def test_failing_battle_does_not_block_other_fights(self):
        self.composition.delete()
        other = Hero.objects.create(name='Other', hero_class=self.hero.hero_class,
            dungeon_run=create_run(), is_in_combat=True)
        run = other.dungeon_run
        run['current_encounter'] = Encounter.create('ogre_guard', 1).to_dict()
        other.dungeon_run = run
        other.save()
        EncounterMonster.objects.create(encounter_definition_key='ogre_guard', monster=self.monster)
        worker = BattleDaemon()
        worker.token = self.token
        with self.assertLogs('battle_daemon', level='ERROR'):
            worker.tick()
        self.assertEqual(Battle.objects.get(hero=self.hero).status, 'PAUSED_ERROR')
        self.assertEqual(Battle.objects.get(hero=other).status, 'ACTIVE')

    def test_failure_after_reward_writes_rolls_back_inventory_and_xp(self):
        from .services import _resolve
        item = Item.objects.create(name='Rollback loot')
        MonsterLoot.objects.create(monster=self.monster, item=item, drop_chance=100)
        battle = self.adopt()
        process_battle(battle.pk, self.token, 0)

        def fail_after_resolution(*args):
            _resolve(*args)
            raise RuntimeError('failed after inventory writes')

        with patch('battle.services._resolve', side_effect=fail_after_resolution):
            with self.assertRaises(RuntimeError):
                for _ in range(20):
                    process_battle(battle.pk, self.token, 1000)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.experience, 0)
        self.assertIsNone(self.hero.inventory_id)
        self.assertFalse(InventoryItem.objects.filter(item=item).exists())
        self.assertEqual(self.fight(battle), 'FINISHED')
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.experience, 17)
        self.assertEqual(InventoryItem.objects.get(item=item).quantity, 1)

    def test_instant_loot_applies_money_and_resources_once_without_stock(self):
        from item.models import Instant
        from django.urls import reverse
        purse = Instant.objects.create(name='Coin purse', money_amount=25, heal_amount=1000, mana_restore=10)
        MonsterLoot.objects.create(monster=self.monster, item=purse, drop_chance=100, min_quantity=3, max_quantity=3)
        Hero.objects.filter(pk=self.hero.pk).update(money=11, current_mana=10)
        battle = self.adopt()
        self.assertEqual(self.fight(battle), 'FINISHED')
        self.hero.refresh_from_db()
        battle.refresh_from_db()
        self.assertEqual(self.hero.money, 86)
        self.assertEqual(self.hero.current_health, self.hero.max_health)
        self.assertEqual(self.hero.current_mana, 40)
        self.assertIsNone(self.hero.inventory_id)
        self.assertFalse(InventoryItem.objects.filter(item=purse).exists())
        self.assertEqual(self.hero.dungeon_run['last_result']['money_change'], 75)
        self.assertEqual(battle.checkpoint['combatants']['hero']['health'], self.hero.current_health)
        self.assertEqual(battle.events.filter(event_type='instant_use').count(), 1)
        self.assertEqual(battle.events.last().sequence, battle.last_event_sequence)
        battle.full_clean()
        session = self.client.session; session['hero_id'] = self.hero.pk; session.save()
        data = self.client.get(reverse('battle:state', args=[battle.pk])).json()
        self.assertEqual(data['result']['money_change'], 75)
        process_battle(battle.pk, self.token, 1000)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 86)

    def test_instant_money_reward_rolls_back_on_resolution_failure(self):
        from item.models import Instant
        from .services import _resolve
        purse = Instant.objects.create(name='Rollback purse', money_amount=50)
        MonsterLoot.objects.create(monster=self.monster, item=purse, drop_chance=100)
        battle = self.adopt()
        process_battle(battle.pk, self.token, 0)

        def fail_after_reward(*args):
            _resolve(*args)
            raise RuntimeError('failure after instant use')

        with patch('battle.services._resolve', side_effect=fail_after_reward):
            with self.assertRaises(RuntimeError):
                for _ in range(20):
                    process_battle(battle.pk, self.token, 1000)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 0)
        self.assertFalse(battle.events.filter(event_type='instant_use').exists())
        self.assertEqual(self.fight(battle), 'FINISHED')
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.money, 50)
