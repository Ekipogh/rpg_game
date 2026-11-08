"""Deployment failure and archive-safety checks; no root or server required."""
from contextlib import ExitStack
import importlib.util
import io
import json
from pathlib import Path
import platform
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('deploy', Path(__file__).resolve().parents[1] / 'deploy.py')
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'app'
        self.data = self.base / 'data'
        self.backups = self.base / 'backups'
        for directory in (self.root / 'releases', self.data, self.backups):
            directory.mkdir(parents=True)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in [('ROOT', self.root), ('DATA', self.data), ('BACKUPS', self.backups)]:
            self.stack.enter_context(patch.object(deploy, name, value))

    def archive(self, entries):
        archive = self.base / 'artifact.tar.gz'
        with tarfile.open(archive, 'w:gz') as bundle:
            for name, kind in entries:
                member = tarfile.TarInfo(name)
                if kind == 'link':
                    member.type = tarfile.SYMTYPE
                    member.linkname = '/etc/passwd'
                    bundle.addfile(member)
                else:
                    member.size = 2
                    bundle.addfile(member, io.BytesIO(b'ok'))
        return archive

    def test_rejects_traversal_links_duplicate_and_injected_venv(self):
        for entries in [('../escape',), ('/absolute',), ('.venv/bin/python',)]:
            with self.subTest(entries=entries):
                archive = self.archive([(entries[0], 'file')])
                with self.assertRaises(ValueError):
                    deploy.unpack(archive, self.base / 'extracted')
        for entries in [[('link', 'link')], [('file', 'file'), ('./file', 'file')]]:
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    deploy.unpack(self.archive(entries), self.base / 'extracted')
        self.assertFalse((self.base / 'escape').exists())

    def test_regular_archive_extracts(self):
        destination = self.base / 'extracted'
        destination.mkdir()
        deploy.unpack(self.archive([('game/settings.py', 'file')]), destination)
        self.assertEqual((destination / 'game/settings.py').read_text(), 'ok')

    def make_release(self, location):
        location.mkdir(exist_ok=True)
        (location / 'RELEASE.json').write_text(json.dumps({
            'revision': 'a' * 40, 'python': '3.14', 'machine': platform.machine(),
        }))
        (location / 'manage.py').touch()
        (location / 'requirements-resolved.txt').touch()
        (location / 'wheels').mkdir(exist_ok=True)

    def test_manifest_rejects_wrong_architecture(self):
        release = self.root / 'releases' / 'old'
        self.make_release(release)
        with patch.object(deploy.platform, 'machine', return_value='wrong-machine'):
            with self.assertRaises(ValueError):
                deploy.validate_manifest(release)

    def test_manifest_rejects_previous_python_runtime(self):
        release = self.root / 'releases' / 'old-runtime'
        self.make_release(release)
        manifest_path = release / 'RELEASE.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['python'] = '3.12'
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Python 3.14'):
            deploy.validate_manifest(release)

    def test_database_and_state_backup_preserves_original(self):
        (self.data / 'db.sqlite3').write_bytes(b'database-before-migration')
        (self.data / 'healing_state.json').write_text('{}')
        saved = deploy.backup(None)
        (self.data / 'db.sqlite3').write_bytes(b'changed')
        self.assertEqual((saved / 'data/db.sqlite3').read_bytes(), b'database-before-migration')
        self.assertEqual((saved / 'data/healing_state.json').read_text(), '{}')

    def deployment_mocks(self, failure=None):
        artifact = self.base / 'artifact.tar.gz'
        artifact.write_bytes(b'placeholder')
        self.stack.enter_context(patch.object(deploy, 'unpack', side_effect=lambda _, dest: self.make_release(dest)))
        self.stack.enter_context(patch.object(deploy, 'stage_artifact', side_effect=shutil.copyfile))
        self.stack.enter_context(patch.object(deploy, 'run'))
        app = self.stack.enter_context(patch.object(deploy, 'app_run'))
        if failure:
            def execute(_release, *args):
                if failure in args:
                    (self.data / 'db.sqlite3').write_bytes(b'partial migration')
                    raise RuntimeError('migration failed')
            app.side_effect = execute
        stopped = self.stack.enter_context(patch.object(deploy, 'stop_services'))
        switched = self.stack.enter_context(patch.object(deploy, 'switch'))
        ready = self.stack.enter_context(patch.object(deploy, 'start_and_verify'))
        self.stack.enter_context(patch.object(deploy, 'current_release', return_value=self.root / 'releases/old'))
        return artifact, app, stopped, switched, ready

    def test_failed_migration_keeps_backup_and_does_not_start_services(self):
        (self.data / 'db.sqlite3').write_bytes(b'original')
        artifact, _, stopped, switched, ready = self.deployment_mocks('migrate')
        with self.assertRaisesRegex(RuntimeError, 'migration failed'):
            deploy.deploy(artifact)
        self.assertEqual(stopped.call_count, 2)
        switched.assert_not_called()
        ready.assert_not_called()
        self.assertEqual(next(self.backups.glob('*/data/db.sqlite3')).read_bytes(), b'original')

    def test_existing_install_does_not_overwrite_custom_classes(self):
        (self.data / 'db.sqlite3').write_bytes(b'original')
        artifact, app, _, switched, ready = self.deployment_mocks()
        deploy.deploy(artifact)
        calls = [str(call) for call in app.call_args_list]
        self.assertFalse(any('setup_classes' in call for call in calls))
        switched.assert_called_once()
        ready.assert_called_once()

    def test_first_install_seeds_content(self):
        artifact, app, _, _, _ = self.deployment_mocks()
        deploy.deploy(artifact)
        self.assertTrue(any('setup_classes' in str(call) for call in app.call_args_list))
        self.assertTrue(any('setup_battle_content' in str(call) for call in app.call_args_list))

    def test_preparation_failure_leaves_running_services_alone(self):
        artifact, app, stopped, switched, ready = self.deployment_mocks()
        app.side_effect = RuntimeError('dependency installation failed')
        with self.assertRaisesRegex(RuntimeError, 'dependency installation failed'):
            deploy.deploy(artifact)
        stopped.assert_not_called()
        switched.assert_not_called()
        ready.assert_not_called()
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_failed_readiness_stops_services_and_keeps_recovery_snapshot(self):
        (self.data / 'db.sqlite3').write_bytes(b'original')
        artifact, _, stopped, switched, ready = self.deployment_mocks()
        ready.side_effect = RuntimeError('wrong revision')
        with self.assertRaisesRegex(RuntimeError, 'wrong revision'):
            deploy.deploy(artifact)
        switched.assert_called_once()
        self.assertEqual(stopped.call_count, 2)
        self.assertEqual(next(self.backups.glob('*/data/db.sqlite3')).read_bytes(), b'original')

    def test_readiness_rejects_wrong_revision(self):
        release = self.root / 'releases/new'
        self.make_release(release)
        with patch.object(deploy, 'run') as systemctl, \
                patch.object(deploy.time, 'sleep'), \
                patch.object(deploy.urllib.request, 'urlopen', side_effect=lambda *a, **k:
                             io.BytesIO(b'{"status":"ok","revision":"wrong"}')):
            with self.assertRaisesRegex(RuntimeError, 'Readiness check failed'):
                deploy.start_and_verify(release)
        self.assertFalse(any('is-active' in call.args for call in systemctl.call_args_list))

    def test_artifact_is_read_with_callers_permissions(self):
        with patch.dict(deploy.os.environ, {'SUDO_USER': 'teamcity'}), \
                patch.object(deploy.subprocess, 'run') as command:
            deploy.stage_artifact(Path('/agent/artifact'), self.base / 'staging')
        self.assertEqual(command.call_args.args[0], [
            '/usr/sbin/runuser', '-u', 'teamcity', '--', '/bin/cat', '--', str(Path('/agent/artifact'))])

    def test_restore_preserves_failed_data_then_restores_matching_release(self):
        previous = self.root / 'releases/old'
        self.make_release(previous)
        (self.data / 'db.sqlite3').write_bytes(b'before')
        saved = deploy.backup(previous)
        (self.data / 'db.sqlite3').write_bytes(b'after')
        with patch.object(deploy, 'stop_services'), patch.object(deploy, 'run'), \
                patch.object(deploy, 'current_release', return_value=previous), \
                patch.object(deploy, 'switch') as switched, \
                patch.object(deploy, 'start_and_verify') as ready:
            deploy.restore(saved.name)
        self.assertEqual((self.data / 'db.sqlite3').read_bytes(), b'before')
        preserved = [path for path in self.backups.iterdir() if path != saved]
        self.assertEqual((preserved[0] / 'data/db.sqlite3').read_bytes(), b'after')
        switched.assert_called_once_with(previous)
        ready.assert_called_once_with(previous)

    def test_restore_refuses_arbitrary_path(self):
        with self.assertRaises(ValueError):
            deploy.restore('../../etc')


if __name__ == '__main__':
    unittest.main()
