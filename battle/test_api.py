"""API and dungeon integration tests for live battles."""
import json
from unittest.mock import patch
from uuid import uuid4

from django.db import transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from hero.dungeon import apply_action, create_run, enter_or_resume, resolve_encounter
from hero.encounters import Encounter
from hero.models import Hero, HeroClass, Monster
from .models import Battle, BattleCommand, EncounterMonster
from .services import acquire_lease, process_battle


class BattleApiTests(TestCase):
    def setUp(self):
        choice = patch('hero.dungeon.random.choice', return_value='goblin_ambush')
        choice.start()
        self.addCleanup(choice.stop)
        cls = HeroClass.objects.create(name='Warrior')
        self.hero = Hero.objects.create(name='Explorer', hero_class=cls, attack=1000)
        self.other = Hero.objects.create(name='Other', hero_class=cls)
        self.monster = Monster.objects.create(name='Goblin', max_health=10, attack=0, experience_reward=7)
        EncounterMonster.objects.create(encounter_definition_key='goblin_ambush', monster=self.monster)
        self.assertEqual(enter_or_resume(self.hero.pk), 'success')
        self.battle = Battle.objects.get(hero=self.hero)
        session = self.client.session
        session['hero_id'] = self.hero.pk
        session.save()
        self.state_url = reverse('battle:state', args=[self.battle.pk])
        self.commands_url = reverse('battle:commands', args=[self.battle.pk])
        acquire_lease('test-worker')

    def post(self, command_type='set_movement_policy', payload=None, id=None):
        return self.client.post(self.commands_url, data=json.dumps({
            'id': str(id or uuid4()), 'command_type': command_type,
            'payload': payload if payload is not None else {'policy': 'hold'}}), content_type='application/json')

    def start_worker(self):
        process_battle(self.battle.pk, 'test-worker', 0)

    def test_fight_items_are_owned_consumables_and_refresh_after_use(self):
        from item.models import Consumable, Instant, Weapon, InventoryItem
        potion = Consumable.objects.create(name='Fight potion', heal_amount=10, mana_restore=5)
        self.hero.add_to_inventory(potion, 2)
        self.hero.add_to_inventory(Weapon.objects.create(name='Spare sword'))
        other_potion = Consumable.objects.create(name='Other potion')
        self.other.add_to_inventory(other_potion)
        instant = Instant.objects.create(name='Automatic item')
        self.hero.refresh_from_db()
        InventoryItem.objects.create(inventory=self.hero.inventory, item=instant, quantity=1)
        Hero.objects.filter(pk=self.hero.pk).update(current_health=50, current_mana=10)
        self.start_worker()
        items = self.client.get(self.state_url).json()['items']
        self.assertEqual(items, [{'id': potion.pk, 'name': 'Fight potion', 'quantity': 2,
            'heal_amount': 10, 'mana_restore': 5,
            'use_url': reverse('use_item_api', args=[potion.pk])}])
        for remaining in (1, 0):
            response = self.client.post(items[0]['use_url'])
            self.assertEqual(response.status_code, 200, response.content)
            current = self.client.get(self.state_url).json()
            self.assertEqual([i['quantity'] for i in current['items']], [remaining] if remaining else [])
        process_battle(self.battle.pk, 'test-worker', 0)

    def test_entry_creates_pending_battle_atomically_and_resumes_once(self):
        self.assertEqual(self.battle.status, 'PENDING')
        self.hero.refresh_from_db()
        revision = self.hero.dungeon_revision
        Hero.objects.filter(pk=self.hero.pk).update(current_health=1)
        self.assertEqual(enter_or_resume(self.hero.pk), 'success')
        self.assertEqual(Battle.objects.filter(hero=self.hero).count(), 1)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.dungeon_revision, revision)
        with patch('battle.models.Battle.objects.get_or_create', side_effect=RuntimeError('creation failed')):
            with self.assertRaises(RuntimeError):
                enter_or_resume(self.other.pk)
        self.other.refresh_from_db()
        self.assertEqual(self.other.dungeon_run, {})

    def test_read_endpoints_are_read_only_and_private(self):
        before = (self.battle.revision, self.battle.checkpoint)
        for _ in range(2):
            response = self.client.get(self.state_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['status'], 'PENDING')
            self.assertIn('no-store', response['Cache-Control'])
        self.battle.refresh_from_db()
        self.assertEqual((self.battle.revision, self.battle.checkpoint), before)
        self.assertEqual(Client().get(self.state_url).status_code, 404)
        session = self.client.session; session['hero_id'] = self.other.pk; session.save()
        self.assertEqual(self.client.get(self.state_url).status_code, 404)
        self.assertEqual(self.post().status_code, 404)

    def test_state_contains_display_data_without_seed_or_reward_tables(self):
        self.start_worker()
        response = self.client.get(self.state_url)
        data = response.json()
        self.assertTrue(data['worker_available'])
        self.assertEqual(len(data['combatants']), 2)
        self.assertEqual(data['combatants'][0]['name'], 'Explorer')
        for private in ('initial_rng_seed', 'drop_chance_bp', 'rng_version'):
            self.assertNotIn(private, response.content.decode())

    def test_command_idempotency_order_and_changed_payload_conflict(self):
        key = uuid4()
        first = self.post(id=key)
        self.assertEqual(first.status_code, 202)
        duplicate = self.post(id=key)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(first.json(), duplicate.json())
        self.assertEqual(self.post(id=key, payload={'policy': 'approach'}).status_code, 409)
        second = self.post(payload={'policy': 'approach'})
        self.assertEqual(second.json()['sequence'], first.json()['sequence'] + 1)
        self.assertEqual(BattleCommand.objects.count(), 2)
        self.start_worker()
        data = self.client.get(self.state_url).json()
        self.assertTrue(all(c['status'] == 'ACCEPTED' for c in data['commands']))
        self.assertEqual(data['combatants'][0]['movement_policy'], 'approach')

    def test_invalid_commands_leave_no_receipts(self):
        for command_type, payload in [('heal', {}), ('set_movement_policy', {'policy': 'retreat'}),
                                      ('select_target', {'target_id': 'enemy:99'}),
                                      ('set_movement_policy', {'policy': 'hold', 'damage': 99})]:
            self.assertEqual(self.post(command_type, payload).status_code, 400)
        for body in ('bad', '[]', '{}', '{"id": 1}', 'x'*4097):
            self.assertEqual(self.client.post(self.commands_url, data=body, content_type='application/json').status_code, 400)
        self.assertEqual(BattleCommand.objects.count(), 0)

    def test_maintain_range_command_is_accepted(self):
        response = self.post(payload={'policy': 'maintain_range'})
        self.assertEqual(response.status_code, 202)
        self.start_worker()
        data = self.client.get(self.state_url).json()
        self.assertEqual(data['combatants'][0]['movement_policy'],
                         'maintain_range')
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.movement_policy, 'maintain_range')

    def test_csrf_and_http_methods(self):
        secure = Client(enforce_csrf_checks=True)
        session = secure.session; session['hero_id'] = self.hero.pk; session.save()
        data = {'id': str(uuid4()), 'command_type': 'set_movement_policy', 'payload': {'policy': 'hold'}}
        self.assertEqual(secure.post(self.commands_url, data=json.dumps(data), content_type='application/json').status_code, 403)
        secure.get(self.state_url)
        response = secure.post(self.commands_url, data=json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=secure.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.client.get(self.commands_url).status_code, 405)
        self.assertEqual(self.client.post(self.state_url).status_code, 405)

    def test_events_cursor_pagination_and_older_pages(self):
        self.start_worker()
        process_battle(self.battle.pk, 'test-worker', 1000)
        url = reverse('battle:events', args=[self.battle.pk])
        first = self.client.get(url, {'limit': 1}).json()
        self.assertEqual(first['next_seq'], 1)
        self.assertTrue(first['has_more'])
        second = self.client.get(url, {'after_seq': 1, 'limit': 1}).json()
        self.assertEqual(second['events'][0]['sequence'], 2)
        older = self.client.get(url, {'before_seq': 3, 'limit': 1}).json()
        self.assertEqual(older['events'][0]['sequence'], 2)
        self.assertTrue(older['has_older'])
        for query in ({'after_seq': -1}, {'limit': 0}, {'limit': 101}, {'before_seq': 'bad'}):
            self.assertEqual(self.client.get(url, query).status_code, 400)

    def test_full_fight_result_paths_and_no_manual_bypass(self):
        self.hero.refresh_from_db()
        self.assertEqual(apply_action(self.hero.pk, 'resolve', self.hero.dungeon_revision), 'invalid')
        with self.assertRaises(ValueError):
            resolve_encounter(self.hero.dungeon_run, 100, 100, 0)
        self.start_worker()
        for _ in range(10):
            if process_battle(self.battle.pk, 'test-worker', 1000) == 'FINISHED':
                break
        data = self.client.get(self.state_url).json()
        self.assertEqual(data['outcome'], 'VICTORY')
        self.assertEqual(data['next_url'], reverse('dungeon'))
        self.assertEqual(data['result']['experience'], 7)
        self.assertEqual(self.post().status_code, 409)
        self.hero.refresh_from_db()
        run = self.hero.dungeon_run
        run['path_left'] = Encounter.create('goblin_ambush', 2).to_dict()
        Hero.objects.filter(pk=self.hero.pk).update(dungeon_run=run)
        self.assertEqual(apply_action(self.hero.pk, 'choose', self.hero.dungeon_revision, 0), 'success')
        self.assertEqual(Battle.objects.filter(hero=self.hero).count(), 2)
        self.assertEqual(Battle.objects.filter(hero=self.hero, status='PENDING').count(), 1)

    def test_paused_error_hides_operational_details(self):
        Battle.objects.filter(pk=self.battle.pk).update(status='PAUSED_ERROR', error_message='private configuration path')
        response = self.client.get(self.state_url)
        self.assertIn('contact', response.json()['error'])
        self.assertNotContains(response, 'private configuration path')
        self.assertEqual(self.post().status_code, 409)

    def test_loot_report_groups_items_and_renders_names_and_quantities(self):
        from hero.models import MonsterLoot
        from item.models import Item, InventoryItem
        item = Item.objects.create(name='Relic <rare>')
        for quantity in (2, 3):
            MonsterLoot.objects.create(monster=self.monster, item=item, drop_chance=100,
                                      min_quantity=quantity, max_quantity=quantity)
        self.start_worker()
        for _ in range(15):
            if process_battle(self.battle.pk, 'test-worker', 1000) == 'FINISHED':
                break
        expected = [{'item_id': item.pk, 'name': item.name, 'quantity': 5}]
        self.assertEqual(self.client.get(self.state_url).json()['result']['loot'], expected)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.dungeon_run['last_result']['loot'], expected)
        response = self.client.get(reverse('dungeon'))
        self.assertContains(response, 'Loot received:')
        self.assertContains(response, 'Relic &lt;rare&gt; &times; 5')
        self.assertEqual(InventoryItem.objects.get(inventory=self.hero.inventory, item=item).quantity, 5)
        self.assertNotContains(response, 'No loot received.')

    def test_empty_loot_report(self):
        self.start_worker()
        for _ in range(15):
            if process_battle(self.battle.pk, 'test-worker', 1000) == 'FINISHED':
                break
        self.assertEqual(self.client.get(self.state_url).json()['result']['loot'], [])
        self.assertContains(self.client.get(reverse('dungeon')), 'No loot received.')

    def test_ui_movement_card_and_get_does_not_create_missing_battle(self):
        response = self.client.get(reverse('dungeon_fight'))
        self.assertContains(response, 'Movement policy')
        self.assertContains(response, 'data-policy="maintain_range"')
        self.assertContains(response, '>Maintain Range<')
        self.assertContains(response, self.state_url)
        self.assertNotContains(response, '>Dungeon run<')
        self.assertNotContains(response, 'value="resolve"')
        self.battle.delete()
        response = self.client.get(reverse('dungeon_fight'))
        self.assertContains(response, 'restore this encounter')
        self.assertEqual(Battle.objects.count(), 0)


class StarterContentTests(TestCase):
    def test_setup_is_idempotent_and_preserves_custom_content(self):
        from django.core.management import call_command
        from io import StringIO
        custom = Monster.objects.create(name='Goblin', attack=123)
        for _ in range(2):
            call_command('setup_battle_content', stdout=StringIO())
        custom.refresh_from_db()
        self.assertEqual(custom.attack, 123)
        self.assertEqual(Monster.objects.count(), 3)
        self.assertEqual(EncounterMonster.objects.count(), 3)
        self.assertEqual(EncounterMonster.objects.get(encounter_definition_key='goblin_ambush').monster_id, custom.pk)


class CommandConcurrencyTests(TransactionTestCase):
    def test_concurrent_producers_allocate_distinct_sequences(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from time import sleep
        from django.db import OperationalError, connections
        from .services import submit_command
        hero = Hero.objects.create(name='Concurrent', hero_class=HeroClass.objects.create(name='Warrior'))
        monster = Monster.objects.create(name='Concurrent enemy')
        EncounterMonster.objects.create(encounter_definition_key='goblin_ambush', monster=monster)
        with patch('hero.dungeon.random.choice', return_value='goblin_ambush'):
            enter_or_resume(hero.pk)
        battle = Battle.objects.get(hero=hero)
        barrier = Barrier(2)

        def producer():
            key = uuid4()
            barrier.wait(timeout=5)
            try:
                for attempt in range(20):
                    try:
                        command, _ = submit_command(battle.pk, hero.pk, key, 'set_movement_policy', {'policy': 'hold'})
                        return command.sequence
                    except OperationalError:
                        sleep(0.01)
                raise AssertionError('Concurrent producer could not commit')
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: producer(), range(2)))
        self.assertEqual(sorted(results), [1, 2])
        self.assertEqual(battle.commands.count(), 2)
