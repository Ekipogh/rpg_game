#!/usr/bin/python3
"""Root-owned, local deployment entry point. Application code runs as rpg-game."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path('/opt/rpg_game')
DATA = Path('/var/lib/rpg_game')
BACKUPS = Path('/var/backups/rpg_game')
ACCOUNT = 'rpg-game'
SERVICES = ('rpg_game', 'rpg_game-battle', 'rpg_game-healing')
PYTHON = '/usr/bin/python3.12'


def run(*args):
    subprocess.run(args, check=True)


def app_run(release, *args):
    # env file is administrator-owned shell syntax. Never source build content as root.
    run('/usr/sbin/runuser', '-u', ACCOUNT, '--', '/bin/bash', '-c',
        'set -euo pipefail; set -a; source /etc/rpg_game/environment; set +a; '
        'cd "$1"; shift; exec "$@"', 'rpg-game', str(release), *map(str, args))


@contextmanager
def deployment_lock():
    import fcntl
    with open('/run/rpg-game-deploy.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def current_release():
    current = ROOT / 'current'
    if not current.is_symlink():
        if current.exists():
            raise ValueError('current must be a symlink, not a directory')
        return None
    release = current.resolve(strict=True)
    if release.parent != ROOT / 'releases':
        raise ValueError('current points outside the release directory')
    return release


def switch(release):
    temporary = ROOT / 'current.new'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(release)
    temporary.replace(ROOT / 'current')


def identifier():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def unpack(archive, destination):
    # Extract only plain files/directories into a new root-owned directory.
    # Reject links, device nodes, traversal, duplicates, and injected venvs.
    seen = set()
    with tarfile.open(archive, 'r:gz') as bundle:
        members = bundle.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts
                    or not (member.isfile() or member.isdir())
                    or (path.parts and path.parts[0] in ('.venv', 'staticfiles'))):
                raise ValueError(f'Unsafe artifact entry: {member.name}')
            normalized = str(path)
            if normalized in seen:
                raise ValueError(f'Duplicate artifact entry: {member.name}')
            seen.add(normalized)
        bundle.extractall(destination, members=members, filter='data')


def validate_manifest(release):
    manifest = json.loads((release / 'RELEASE.json').read_text())
    if not re.fullmatch(r'[0-9a-f]{40}', manifest['revision']):
        raise ValueError('Invalid release revision')
    if manifest['python'] != '3.12' or manifest['machine'] != platform.machine():
        raise ValueError('Build and target must use Python 3.12 and the same architecture')
    for filename in ('manage.py', 'requirements-resolved.txt', 'wheels'):
        if not (release / filename).exists():
            raise ValueError(f'Incomplete artifact: missing {filename}')
    return manifest


def stage_artifact(source, destination):
    # Read with the invoking operator's permissions, not root's. This helper
    # must not let an agent use artifact errors to inspect root-only files.
    caller = os.environ.get('SUDO_USER', 'root')
    with destination.open('wb') as output:
        subprocess.run(['/usr/sbin/runuser', '-u', caller, '--',
                        '/bin/cat', '--', str(source)], stdout=output, check=True)


def stop_services():
    run('/usr/bin/systemctl', 'stop', *SERVICES)


def start_and_verify(release):
    run('/usr/bin/systemd-analyze', 'verify',
        *(f'/etc/systemd/system/{service}.service' for service in SERVICES))
    run('/usr/bin/systemctl', 'start', *SERVICES)
    expected = json.loads((release / 'RELEASE.json').read_text())['revision']
    for attempt in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=2) as response:
                body = json.load(response)
            if body.get('status') == 'ok' and body.get('revision') == expected:
                # Check again after workers have had time to fail on startup.
                time.sleep(2)
                run('/usr/bin/systemctl', 'is-active', '--quiet', *SERVICES)
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError('Readiness check failed or the wrong revision is serving port 8000')


def backup(previous):
    if any(entry.is_symlink() for entry in DATA.rglob('*')):
        raise ValueError('Refusing to back up symlinks in the application data directory')
    destination = BACKUPS / identifier()
    destination.mkdir(mode=0o700)
    shutil.copytree(DATA, destination / 'data', symlinks=False)
    (destination / 'backup.json').write_text(json.dumps({
        'previous_release': str(previous) if previous else None,
    }))
    return destination


def deploy(artifact):
    previous = current_release()
    release = ROOT / 'releases' / identifier()
    release.mkdir(mode=0o755)
    # Copy to root-only staging before inspection so the agent cannot mutate the
    # archive between validation and extraction.
    with tempfile.TemporaryDirectory(prefix='rpg-game-') as staging:
        frozen = Path(staging) / 'release.tar.gz'
        stage_artifact(artifact, frozen)
        unpack(frozen, release)
    manifest = validate_manifest(release)
    run('/usr/bin/chown', '-R', f'{ACCOUNT}:{ACCOUNT}', str(release))
    app_run(release, PYTHON, '-m', 'venv', release / '.venv')
    python = release / '.venv/bin/python'
    app_run(release, python, '-m', 'pip', 'install', '--no-index',
            '--find-links', release / 'wheels', '-r', release / 'requirements-resolved.txt')
    app_run(release, python, '-m', 'pip', 'check')
    app_run(release, python, 'manage.py', 'check')
    app_run(release, python, 'manage.py', 'collectstatic', '--noinput')
    saved = None
    first_install = not (DATA / 'db.sqlite3').exists()
    try:
        stop_services()
        saved = backup(previous)
        print(f'Backup: {saved}', flush=True)
        app_run(release, python, 'manage.py', 'migrate', '--noinput')
        if first_install:
            app_run(release, python, 'manage.py', 'setup_classes')
            app_run(release, python, 'manage.py', 'setup_battle_content')
        switch(release)
        start_and_verify(release)
    except BaseException:
        stop_services()
        print('Deployment failed; services are stopped. No automatic schema rollback.', file=sys.stderr)
        if saved and previous:
            print(f'Recovery: sudo rpg-game-deploy --restore {saved.name}', file=sys.stderr)
        raise
    print(f'Deployed {manifest["revision"]} to {release}', flush=True)


def restore(name):
    if not re.fullmatch(r'\d{8}T\d{12}Z', name):
        raise ValueError('Use a backup ID printed by deployment')
    source = BACKUPS / name
    record = json.loads((source / 'backup.json').read_text())
    if not record['previous_release']:
        raise ValueError('This backup predates the first release; fix and redeploy instead')
    previous = Path(record['previous_release']).resolve(strict=True)
    if previous.parent != ROOT / 'releases':
        raise ValueError('Invalid previous release')
    validate_manifest(previous)
    if not (source / 'data').is_dir():
        raise ValueError('Backup data missing')
    stop_services()
    # Preserve the failed deployment's data before replacing the database.
    preserved = backup(current_release())
    print(f'Preserved current data in {preserved}', flush=True)
    try:
        for entry in DATA.iterdir():
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        shutil.copytree(source / 'data', DATA, dirs_exist_ok=True)
        run('/usr/bin/chown', '-R', f'{ACCOUNT}:{ACCOUNT}', str(DATA))
        switch(previous)
        start_and_verify(previous)
    except BaseException:
        stop_services()
        raise
    print(f'Restored {name}; writes since that backup have been reverted.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--artifact', type=Path)
    group.add_argument('--restore', metavar='BACKUP_ID')
    arguments = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run through sudo')
    with deployment_lock():
        if arguments.artifact:
            deploy(arguments.artifact.resolve(strict=True))
        else:
            restore(arguments.restore)


if __name__ == '__main__':
    main()
