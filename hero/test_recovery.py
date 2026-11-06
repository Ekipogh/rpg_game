from unittest.mock import patch
from django.test import TestCase
from .models import Hero, HeroClass
from .dungeon import enter_or_resume, apply_action
from .recovery import restore_resources
from .windows_tasks import simple_heal_hero, rest_hero


class RecoveryTests(TestCase):
    def setUp(self):
        self.hero = Hero.objects.create(name='Resting', hero_class=HeroClass.objects.create(name='Mage'),
                                        current_health=90, current_mana=40)

    def test_caps_and_requested_fields_only(self):
        restore_resources(self.hero.pk, health_amount=50)
        self.hero.refresh_from_db()
        self.assertEqual((self.hero.current_health, self.hero.current_mana), (100, 40))
        restore_resources(self.hero.pk, mana_amount=50)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.current_mana, 50)
        with self.assertRaises(ValueError):
            restore_resources(self.hero.pk, health_amount=-1)

    def test_suppression_in_both_phases_and_resume(self):
        from .encounters import Encounter
        from .dungeon import create_run
        run = create_run()
        run['current_encounter'] = Encounter.create('spike_pit', 1).to_dict()
        with patch('hero.dungeon.create_run', return_value=run):
            enter_or_resume(self.hero.pk)
        for phase in ('encounter', 'choices'):
            self.hero.refresh_from_db()
            saved = self.hero.dungeon_run
            revision = self.hero.dungeon_revision
            self.assertEqual(saved['phase'], phase)
            self.assertEqual(restore_resources(self.hero.pk, 10, 10), 0)
            self.assertFalse(simple_heal_hero(self.hero.pk))
            self.assertFalse(rest_hero(self.hero.pk))
            self.hero.refresh_from_db()
            self.assertEqual(self.hero.dungeon_run, saved)
            self.assertEqual(self.hero.dungeon_revision, revision)
            if phase == 'encounter':
                apply_action(self.hero.pk, 'resolve', revision)
        apply_action(self.hero.pk, 'retreat', self.hero.dungeon_revision)
        self.assertEqual(restore_resources(self.hero.pk, 1, 1), 1)
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.dungeon_run, {})

    def test_existing_daemon_workers_check_eligibility(self):
        from healing_daemon import HealingDaemon
        daemon = HealingDaemon.__new__(HealingDaemon)
        daemon.running = True
        daemon.heal_interval = daemon.mana_restore_interval = 1
        daemon.healing_heroes = {self.hero.pk: {}}
        daemon.mana_restoring_heroes = {self.hero.pk: {}}
        enter_or_resume(self.hero.pk)
        def stop(_):
            daemon.running = False
        with patch('healing_daemon.time.sleep', side_effect=stop):
            daemon._heal_hero_loop(self.hero.pk)
        daemon.running = True
        with patch('healing_daemon.time.sleep', side_effect=stop):
            daemon._restore_mana_loop(self.hero.pk)
        self.hero.refresh_from_db()
        self.assertEqual((self.hero.current_health, self.hero.current_mana), (90, 40))


    def test_fallback_worker_pauses_and_resumes_without_overwriting_run(self):
        from .windows_tasks import heal_hero_over_time_simple
        enter_or_resume(self.hero.pk)
        self.hero.refresh_from_db()
        saved = self.hero.dungeon_run
        def leave_dungeon(_):
            self.hero.refresh_from_db()
            self.assertIn(self.hero.current_health, (90, 91))
            self.assertEqual(self.hero.dungeon_run, saved)
            Hero.objects.filter(pk=self.hero.pk).update(is_in_combat=False)
        with patch('hero.windows_tasks.threading.Thread') as thread, \
                patch('hero.windows_tasks.time.time', side_effect=[0, 0, 1, 301]), \
                patch('hero.windows_tasks.time.sleep', side_effect=leave_dungeon):
            heal_hero_over_time_simple(self.hero.pk)
            thread.call_args.kwargs['target']()
        self.hero.refresh_from_db()
        self.assertEqual(self.hero.current_health, 91)
        self.assertEqual(self.hero.dungeon_run, saved)
