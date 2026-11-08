"""Persistence constraints and model validation for battles."""
from dataclasses import replace
import json
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from hero.models import Hero, HeroClass, Monster
from .engine import create_battle, snapshot_to_json, state_to_json
from .models import Battle, BattleCommand, BattleEvent, BattleWorkerLease, EncounterMonster
from .test_engine import fixture


class BattleModelTests(TestCase):
    def setUp(self):
        cls = HeroClass.objects.create(name='Warrior')
        self.hero = Hero.objects.create(name='Explorer', hero_class=cls)
        self.other = Hero.objects.create(name='Other', hero_class=cls)
        self.battle = Battle.objects.create(hero=self.hero, encounter_id=uuid4())

    def assert_db_rejects(self, operation):
        with self.assertRaises(IntegrityError), transaction.atomic():
            operation()

    def test_encounter_identity_and_one_open_battle(self):
        self.assert_db_rejects(lambda: Battle.objects.create(hero=self.other, encounter_id=self.battle.encounter_id))
        self.assert_db_rejects(lambda: Battle.objects.create(hero=self.hero, encounter_id=uuid4()))
        self.battle.status = 'FINISHED'
        self.battle.save(update_fields=['status'])
        Battle.objects.create(hero=self.hero, encounter_id=uuid4())
        self.assertEqual(Battle.objects.filter(hero=self.hero).count(), 2)

    def test_events_many_per_battle_and_sequences_scoped(self):
        other = Battle.objects.create(hero=self.other, encounter_id=uuid4())
        for battle, sequence in ((self.battle, 1), (self.battle, 2), (other, 1)):
            BattleEvent.objects.create(battle=battle, sequence=sequence, simulation_time_ms=1000,
                event_type='damage', actor_id='hero', target_id='enemy:0', payload={'damage': 3})
        self.assertEqual(self.battle.events.count(), 2)
        event = self.battle.events.first()
        self.assertEqual((event.actor_id, event.target_id), ('hero', 'enemy:0'))
        self.assert_db_rejects(lambda: BattleEvent.objects.create(battle=self.battle, sequence=1,
            simulation_time_ms=2000, event_type='move'))

    def test_commands_scoped_and_uuid_deduplication(self):
        other = Battle.objects.create(hero=self.other, encounter_id=uuid4())
        key = uuid4()
        command = BattleCommand.objects.create(id=key, battle=self.battle, sequence=1, command_type='select_target')
        BattleCommand.objects.create(battle=other, sequence=1, command_type='select_target')
        self.assertEqual(command.status, 'QUEUED')
        self.assert_db_rejects(lambda: BattleCommand.objects.create(id=key, battle=other, sequence=2, command_type='select_target'))
        self.assert_db_rejects(lambda: BattleCommand.objects.create(battle=self.battle, sequence=1, command_type='select_target'))

    def test_nonnegative_values_enforced_in_database(self):
        for field in ('revision', 'last_event_sequence', 'last_processed_command_sequence'):
            self.assert_db_rejects(lambda field=field: Battle.objects.filter(pk=self.battle.pk).update(**{field: -1}))
        self.assert_db_rejects(lambda: BattleEvent.objects.create(battle=self.battle, sequence=1,
            simulation_time_ms=-1, event_type='move'))
        self.assert_db_rejects(lambda: BattleCommand.objects.create(battle=self.battle, sequence=1,
            command_type='select_target', execute_at_ms=-1))

    def test_status_constraints_and_defaults(self):
        self.assertEqual(self.battle.status, 'PENDING')
        self.assertIsNone(self.battle.resolved_at)
        self.assert_db_rejects(lambda: Battle.objects.filter(pk=self.battle.pk).update(status='INVALID'))
        self.assert_db_rejects(lambda: Battle.objects.filter(pk=self.battle.pk).update(outcome='INVALID'))

    def test_lease_keeps_subsecond_timestamps(self):
        now = timezone.now().replace(microsecond=123456)
        lease = BattleWorkerLease.objects.create(name='battle-worker', owner_token='token', expires_at=now, heartbeat_at=now)
        lease.refresh_from_db()
        self.assertEqual(lease.expires_at, now)
        self.assertEqual(lease.heartbeat_at, now)

    def activate(self):
        snapshot = replace(fixture(), battle_id=str(self.battle.pk), encounter_id=str(self.battle.encounter_id))
        self.battle.snapshot = json.loads(snapshot_to_json(snapshot))
        self.battle.checkpoint = json.loads(state_to_json(snapshot, create_battle(snapshot)))
        self.battle.status = 'ACTIVE'

    def test_valid_engine_checkpoint(self):
        self.activate()
        self.battle.full_clean()

    def test_invalid_or_missing_engine_state_rejected(self):
        self.battle.status = 'ACTIVE'
        with self.assertRaises(ValidationError):
            self.battle.full_clean()
        self.activate()
        self.battle.checkpoint['combatants']['hero']['health'] = -1
        with self.assertRaises(ValidationError):
            self.battle.full_clean()

    def test_snapshot_identity_and_version_rejected(self):
        for key, value in (('schema_version', 999), ('battle_id', 'other'), ('encounter_id', str(uuid4()))):
            self.activate()
            self.battle.snapshot[key] = value
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.battle.full_clean()

    def test_checkpoint_cursor_and_lifecycle_mismatch(self):
        self.activate()
        self.battle.last_event_sequence = 1
        with self.assertRaises(ValidationError):
            self.battle.full_clean()
        self.battle.last_event_sequence = 0
        self.battle.status = 'FINISHED'
        with self.assertRaises(ValidationError):
            self.battle.full_clean()


class EncounterMonsterTests(TestCase):
    def setUp(self):
        self.monster = Monster.objects.create(name='Goblin')

    def test_composition_validation(self):
        entry = EncounterMonster(encounter_definition_key='goblin_ambush', monster=self.monster, quantity=2)
        entry.full_clean()
        entry.save()
        entry.full_clean()  # Updating must not count itself twice.
        extra = EncounterMonster(encounter_definition_key='goblin_ambush', monster=self.monster,
                                 quantity=2, position_order=1)
        with self.assertRaises(ValidationError):
            extra.full_clean()
        extra.quantity = 1
        extra.full_clean()
        extra.save()
        self.assertEqual(EncounterMonster.objects.count(), 2)

    def test_invalid_definition_and_quantity(self):
        for key in ('unknown', 'spike_pit'):
            entry = EncounterMonster(encounter_definition_key=key, monster=self.monster)
            with self.assertRaises(ValidationError):
                entry.full_clean()
        for quantity in (0, 4):
            with self.assertRaises(IntegrityError), transaction.atomic():
                EncounterMonster.objects.create(encounter_definition_key='goblin_ambush',
                    monster=self.monster, quantity=quantity)

    def test_unique_spawn_order(self):
        EncounterMonster.objects.create(encounter_definition_key='goblin_ambush', monster=self.monster)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EncounterMonster.objects.create(encounter_definition_key='goblin_ambush', monster=self.monster)
