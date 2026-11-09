from copy import deepcopy
from html import unescape
from unittest.mock import patch

from django.test import TestCase, Client, RequestFactory
from django.urls import reverse

from .dungeon import create_run, resolve_encounter, choose_path, apply_action, enter_or_resume
from .encounters import Encounter
from .models import Hero, HeroClass
from .components.home_screen import HomeScreenView


class DungeonTests(TestCase):
    def setUp(self):
        self.hero = Hero.objects.create(name='Explorer', hero_class=HeroClass.objects.create(name='Warrior'))
        session = self.client.session
        session['hero_id'] = self.hero.pk
        session.save()

    def start(self, kind='goblin_ambush'):
        run = create_run()
        run['current_encounter'] = Encounter.create(kind, 1).to_dict()
        with patch('hero.dungeon.create_run', return_value=run):
            self.assertEqual(enter_or_resume(self.hero.pk), 'success')
        self.hero.refresh_from_db()

    def act(self, action, choice=None):
        result = apply_action(self.hero.pk, action, self.hero.dungeon_revision, choice)
        self.hero.refresh_from_db()
        return result

    def test_effects_and_pure_transitions(self):
        cases = [('spike_pit', (3, 8), 94, 0),
                 ('forgotten_cache', None, 100, 20), ('wandering_healer', None, 100, 0)]
        for key, bounds, expected_hp, expected_xp in cases:
            run = create_run()
            run.update(current_floor=2, current_encounter=Encounter.create(key, 2).to_dict())
            original = deepcopy(run)
            with self.subTest(key=key), patch('hero.dungeon.random.randint', return_value=bounds[0] if bounds else 0) as roll:
                updated, hp, xp = resolve_encounter(run, 100, 100, 0)
                self.assertEqual((hp, xp), (expected_hp, expected_xp))
                self.assertEqual(run, original)
                self.assertEqual(updated['phase'], 'choices')
                if bounds:
                    roll.assert_called_once_with(*bounds)
                else:
                    roll.assert_not_called()
                next_run = choose_path(updated, 0)
                self.assertEqual(next_run['current_floor'], 3)
                self.assertEqual(next_run['phase'], 'encounter')
                self.assertEqual(next_run['current_encounter'], updated['path_left'])
        run = create_run()
        run['current_encounter'] = Encounter.create('wandering_healer', 1).to_dict()
        self.assertEqual(resolve_encounter(run, 98, 100, 0)[1], 100)

    def test_entry_resume_refresh_and_component(self):
        request = RequestFactory().post('/')
        request.session = self.client.session
        component = HomeScreenView(component_name='home-screen', component_id='test')
        component.request = request
        self.assertEqual(component.navigate_to_battle().url, reverse('dungeon'))
        self.hero.refresh_from_db()
        saved = deepcopy(self.hero.dungeon_run)
        revision = self.hero.dungeon_revision
        self.assertEqual(enter_or_resume(self.hero.pk), 'success')
        for _ in range(2):
            title = Encounter.from_dict(saved['current_encounter']).definition.title
            self.assertContains(self.client.get(reverse('dungeon'), follow=True), title)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.dungeon_run, saved)
        self.assertEqual(self.hero.dungeon_revision, revision)
        self.assertTrue(self.hero.is_in_combat)

    def test_dungeon_entry_requires_80_percent_health(self):
        self.hero.current_health = 79
        self.hero.save(update_fields=['current_health'])
        self.assertEqual(enter_or_resume(self.hero.pk), 'not_healed')
        self.hero.refresh_from_db()
        self.assertFalse(self.hero.dungeon_run)

        self.hero.current_health = 80
        self.hero.save(update_fields=['current_health'])
        self.assertEqual(enter_or_resume(self.hero.pk), 'success')

    def test_dungeon_button_enabled_at_80_percent_and_disabled_below(self):
        for health, is_enabled in ((79, False), (80, True)):
            with self.subTest(health=health):
                Hero.objects.filter(pk=self.hero.pk).update(current_health=health)
                response = self.client.get(reverse('home'))
                button = 'id="dungeon-button"'
                self.assertContains(response, button)
                button_markup = response.content.decode().split(button, 1)[1].split('>', 1)[0]
                self.assertEqual(' disabled' in button_markup, not is_enabled)

    def test_duplicates_invalid_phases_and_choices(self):
        self.start('spike_pit')
        revision = self.hero.dungeon_revision
        self.assertEqual(self.act('choose', 0), 'invalid')
        self.assertEqual(self.act('retreat'), 'invalid')
        self.assertEqual(self.act('resolve'), 'success')
        snapshot = deepcopy(self.hero.dungeon_run)
        hp = self.hero.current_health
        self.assertEqual(apply_action(self.hero.pk, 'resolve', revision), 'stale')
        self.assertEqual(self.act('resolve'), 'invalid')
        for choice in (None, -1, 2, True, '0'):
            self.assertEqual(self.act('choose', choice), 'invalid')
        self.assertEqual(self.hero.dungeon_run, snapshot)
        self.assertEqual(self.hero.current_health, hp)
        self.assertEqual(self.act('choose', 1), 'success')
        self.assertEqual(self.hero.dungeon_run['current_encounter'], snapshot['path_right'])

    def test_retreat_and_defeat(self):
        self.start('spike_pit')
        self.act('resolve')
        hp = self.hero.current_health
        self.assertEqual(self.act('retreat'), 'retreat')
        self.assertEqual(self.hero.current_health, hp)
        self.assertFalse(self.hero.is_in_combat)
        self.assertEqual(self.hero.dungeon_run, {})
        self.start('spike_pit')
        Hero.objects.filter(pk=self.hero.pk).update(current_health=1, experience=27)
        self.hero.refresh_from_db()
        self.assertEqual(self.act('resolve'), 'defeat')
        self.assertEqual((self.hero.current_health, self.hero.experience), (1, 27))
        self.assertFalse(self.hero.is_in_combat)

    def test_conflicting_resource_change_is_not_overwritten(self):
        self.start('spike_pit')
        from . import dungeon
        original = dungeon.resolve_encounter
        def conflicting(*args):
            result = original(*args)
            Hero.objects.filter(pk=self.hero.pk).update(current_health=77)
            return result
        with patch('hero.dungeon.resolve_encounter', side_effect=conflicting):
            self.assertEqual(self.act('resolve'), 'stale')
        self.assertEqual(self.hero.current_health, 77)
        self.assertEqual(self.hero.dungeon_run['phase'], 'encounter')

    def test_routes_hidden_paths_csrf_and_hero_switch(self):
        self.start('spike_pit')
        self.act('resolve')
        response = self.client.get(reverse('dungeon'))
        for label in ('Left path', 'Right path', 'Retreat'):
            self.assertContains(response, label, count=1)
        self.assertContains(response, f'name="hero_id" value="{self.hero.pk}"', count=2)
        for side in ('path_left', 'path_right'):
            encounter = self.hero.dungeon_run[side]
            self.assertNotContains(response, encounter['id'])
            self.assertNotContains(response, encounter['definition_key'])
        self.assertNotIn('hero', response.context)
        self.assertEqual(self.client.get(reverse('dungeon_action')).status_code, 405)
        secure = Client(enforce_csrf_checks=True)
        session = secure.session
        session['hero_id'] = self.hero.pk
        session.save()
        self.assertEqual(secure.post(reverse('dungeon_action'), {
            'action': 'retreat', 'hero_id': self.hero.pk,
            'revision': self.hero.dungeon_revision}).status_code, 403)
        secure.get(reverse('dungeon'))
        response = secure.post(reverse('dungeon_action'), {'action': 'retreat', 'revision': self.hero.dungeon_revision,
                               'hero_id': self.hero.pk,
                               'csrfmiddlewaretoken': secure.cookies['csrftoken'].value})
        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
        self.assertContains(secure.get(reverse('home')), 'You retreated')
        other = Hero.objects.create(name='Other', hero_class=self.hero.hero_class)
        self.client.get(reverse('select_hero', args=[other.pk]))
        self.assertRedirects(self.client.get(reverse('dungeon')), reverse('home'))
        self.client.get(reverse('select_hero', args=[self.hero.pk]))
        self.start('spike_pit')
        self.assertRedirects(self.client.get(reverse('home')), reverse('dungeon'),
                             fetch_redirect_response=False)

    def test_missing_hero_invalid_forms_and_stale_post(self):
        self.assertRedirects(Client().get(reverse('dungeon')), reverse('index'), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse('dungeon')), reverse('home'))
        self.start()
        for data in ({}, {'revision': 'x'}, {'revision': 1, 'action': 'choose', 'choice': '5'},
                     {'hero_id': 'invalid', 'revision': 1, 'action': 'resolve'}):
            self.assertEqual(self.client.post(reverse('dungeon_action'), data).status_code, 400)
        self.assertRedirects(self.client.post(reverse('dungeon_action'), {
            'action': 'resolve', 'hero_id': self.hero.pk, 'revision': 0}),
            reverse('dungeon'), fetch_redirect_response=False)

    def test_action_rejects_form_from_another_hero_with_matching_revision(self):
        self.start()
        other = Hero.objects.create(name='Other', hero_class=self.hero.hero_class)
        self.assertEqual(enter_or_resume(other.pk), 'success')
        other.refresh_from_db()
        self.assertEqual(self.hero.dungeon_revision, other.dungeon_revision)

        response = self.client.get(reverse('dungeon_fight'))
        self.assertEqual(response.context['hero_id'], self.hero.pk)
        form_data = {
            'action': 'resolve',
            'hero_id': response.context['hero_id'],
            'revision': response.context['revision'],
        }
        original_hero_state = (self.hero.dungeon_run, self.hero.current_health,
                               self.hero.experience, self.hero.dungeon_revision)
        original_other_state = (other.dungeon_run, other.current_health,
                                other.experience, other.dungeon_revision)

        self.client.get(reverse('select_hero', args=[other.pk]))
        response = self.client.post(reverse('dungeon_action'), form_data)

        self.assertEqual(response.status_code, 400)
        self.hero.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(
            (self.hero.dungeon_run, self.hero.current_health,
             self.hero.experience, self.hero.dungeon_revision),
            original_hero_state)
        self.assertEqual(
            (other.dungeon_run, other.current_health,
             other.experience, other.dungeon_revision),
            original_other_state)

    def test_fight_page_displays_live_battle_and_movement_policy(self):
        self.start()

        response = self.client.get(reverse('dungeon_fight'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Goblin ambush')
        self.assertContains(response, 'A goblin blocks your path.')
        self.assertContains(response, 'Battle log')
        self.assertNotContains(response, 'Encounter details')
        self.assertContains(response, 'Encounter started.')
        self.assertContains(response, f'{self.hero.current_health} / {self.hero.max_health} HP')
        self.assertContains(response, f'{self.hero.current_mana} / {self.hero.max_mana} MP')
        self.assertContains(response, 'Skill actions')
        self.assertEqual(
            unescape(response.content.decode()).count('Blocked · No skill equipped'), 3)
        self.assertContains(response, 'data-skill-slot="1" disabled')
        self.assertContains(response, 'data-skill-slot="2" disabled')
        self.assertContains(response, 'data-skill-slot="3" disabled')
        self.assertContains(response, 'css/fight.css')
        self.assertNotContains(response, 'name="action" value="resolve"')
        self.assertContains(response, 'Movement policy')
        self.assertContains(response, 'data-policy="approach"')
        self.assertContains(response, 'data-policy="hold"')
        self.assertNotContains(response, '>Dungeon run<')
        self.assertContains(response, 'js/fight.js')
        self.assertEqual(response.context['hero_id'], self.hero.pk)


    def test_earned_xp_survives_retreat_and_hero_switch(self):
        self.start('forgotten_cache')
        run = self.hero.dungeon_run
        run['current_encounter'] = Encounter.create('forgotten_cache', 1).to_dict()
        Hero.objects.filter(pk=self.hero.pk).update(dungeon_run=run)
        self.hero.refresh_from_db()
        self.assertEqual(self.act('resolve'), 'success')
        self.assertEqual(self.hero.experience, 10)
        saved = deepcopy(self.hero.dungeon_run)
        other = Hero.objects.create(name='Traveller', hero_class=self.hero.hero_class)
        self.client.get(reverse('select_hero', args=[other.pk]))
        self.client.get(reverse('select_hero', args=[self.hero.pk]))
        self.assertContains(self.client.get(reverse('dungeon')), 'Left path')
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.dungeon_run, saved)
        self.assertEqual(self.act('retreat'), 'retreat')
        self.assertEqual(self.hero.experience, 10)

    def test_entry_conflict_does_not_overwrite_resource_changes(self):
        from . import dungeon
        original = dungeon.create_run
        def conflicting():
            run = original()
            Hero.objects.filter(pk=self.hero.pk).update(current_health=88)
            return run
        with patch('hero.dungeon.create_run', side_effect=conflicting):
            self.assertEqual(enter_or_resume(self.hero.pk), 'stale')
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.current_health, 88)
        self.assertFalse(self.hero.dungeon_run)
        self.assertEqual(self.hero.dungeon_revision, 0)

    def test_defeat_message(self):
        self.start('spike_pit')
        Hero.objects.filter(pk=self.hero.pk).update(current_health=1)
        response = self.client.post(reverse('dungeon_action'), {
            'action': 'resolve', 'hero_id': self.hero.pk,
            'revision': self.hero.dungeon_revision}, follow=True)
        self.assertContains(response, 'returned home with 1 HP')

    def test_encounter_pages_and_canonical_navigation(self):
        self.start()
        for key, page in [('goblin_ambush', 'fight'), ('ogre_guard', 'fight'),
                          ('dungeon_guardian', 'fight'), ('forgotten_cache', 'treasure'),
                          ('spike_pit', 'trap'), ('wandering_healer', 'npc')]:
            with self.subTest(key=key):
                from battle.models import Battle
                Battle.objects.all().delete()  # Each subcase constructs a separate saved run.
                run = create_run()
                run['current_encounter'] = Encounter.create(key, 1).to_dict()
                Hero.objects.filter(pk=self.hero.pk).update(dungeon_run=run)
                self.hero.refresh_from_db()
                revision = self.hero.dungeon_revision
                url = reverse('dungeon_' + page)
                self.assertRedirects(self.client.get(reverse('dungeon')), url)
                response = self.client.get(url)
                self.assertTemplateUsed(response, f'hero/encounters/{page}.html')
                if page == 'fight':
                    title = Encounter.from_dict(run['current_encounter']).definition.title
                    self.assertContains(response, title)
                else:
                    self.assertContains(response, 'encounter placeholder')
                self.assertNotContains(response, 'Left path')
                wrong = 'trap' if page != 'trap' else 'fight'
                self.assertRedirects(self.client.get(reverse('dungeon_' + wrong)), url)
                self.hero.refresh_from_db()
                self.assertEqual(self.hero.dungeon_run, run)
                self.assertEqual(self.hero.dungeon_revision, revision)
                response = self.client.post(reverse('dungeon_action'), {
                    'action': 'resolve', 'hero_id': self.hero.pk,
                    'revision': revision}, follow=True)
                if page == 'fight':
                    self.assertEqual(response.status_code, 400)
                    continue
                self.assertTemplateUsed(response, 'hero/dungeon.html')
                self.assertContains(response, 'Choose your next path')
                self.assertNotContains(response, 'encounter placeholder')
                self.assertRedirects(self.client.get(url), reverse('dungeon'))
                self.hero.refresh_from_db()
                response = self.client.post(reverse('dungeon_action'), {
                    'action': 'choose', 'choice': 0,
                    'hero_id': self.hero.pk,
                    'revision': self.hero.dungeon_revision}, follow=True)
                self.hero.refresh_from_db()
                kind = Encounter.from_dict(self.hero.dungeon_run['current_encounter']).kind
                expected = 'fight' if kind == 'battle' else kind
                self.assertEqual(response.request['PATH_INFO'], reverse('dungeon_' + expected))

    def test_encounter_pages_require_active_hero_and_run(self):
        for page in ('fight', 'treasure', 'trap', 'npc'):
            url = reverse('dungeon_' + page)
            self.assertRedirects(Client().get(url), reverse('index'), fetch_redirect_response=False)
            self.assertRedirects(self.client.get(url), reverse('home'))
            self.assertEqual(self.client.post(url).status_code, 405)
