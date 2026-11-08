import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from datetime import datetime

from django.db import OperationalError
from django.test import TestCase, override_settings


class HealthTests(TestCase):
    def test_reports_release_and_disables_caching(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'RELEASE.json').write_text(json.dumps({'revision': 'a' * 40}))
            with override_settings(BASE_DIR=Path(directory)):
                response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'revision': 'a' * 40})
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_unavailable_database_is_not_healthy(self):
        with patch('game.health.connection.cursor', side_effect=OperationalError('offline')):
            response = self.client.get('/health/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})

    def test_post_is_rejected(self):
        self.assertEqual(self.client.post('/health/').status_code, 405)


class HealingRestartTests(TestCase):
    def test_saved_sessions_do_not_prevent_passive_restart(self):
        from healing_daemon import HealingDaemon
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'healing_state.json'
            state.write_text(json.dumps({'7': {'last_heal': '2026-11-08T00:00:00', 'active': True}}))
            with override_settings(DATA_DIR=Path(directory)):
                daemon = HealingDaemon()
            self.assertEqual(daemon.state_file, state)
            self.assertEqual(daemon.healing_heroes, {})
            # Both restored string timestamps and fresh datetime timestamps save.
            daemon.healing_heroes = {
                7: {'last_heal': '2026-11-08T00:00:00'},
                8: {'last_heal': datetime(2026, 11, 8)},
            }
            daemon.save_state()
            saved = json.loads(state.read_text())
            self.assertEqual(saved['7']['last_heal'], '2026-11-08T00:00:00')
            self.assertEqual(saved['8']['last_heal'], '2026-11-08T00:00:00')
