#!/bin/bash
# Build on the same Ubuntu architecture and Python version as the target.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3.14}"
"$PYTHON" - <<'PY'
import sys
if sys.version_info[:2] != (3, 14):
    raise SystemExit('Ubuntu 26.04 releases require Python 3.14')
PY
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf -- "$BUILD_DIR"' EXIT
mkdir "$BUILD_DIR/package"
git archive HEAD | tar -x -C "$BUILD_DIR/package"
REVISION="$(git rev-parse HEAD)"
# All tests/installations use the archived revision, not loose checkout files.
OUTPUT_DIR="$PWD/dist"
cd "$BUILD_DIR/package"
"$PYTHON" -m venv "$BUILD_DIR/venv"
PY="$BUILD_DIR/venv/bin/python"
"$PY" -m pip install -r requirements-production.txt
"$PY" -m pip check
# Test in an isolated data directory; never touch a live SQLite database.
export RPG_DATA_DIR="$BUILD_DIR/data"
mkdir "$RPG_DATA_DIR"
export DJANGO_DEBUG=False DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
export DJANGO_SECRET_KEY=build-only-not-a-production-secret
"$PY" -X utf8 manage.py check
"$PY" -X utf8 manage.py makemigrations --check --dry-run
"$PY" -X utf8 manage.py test
"$PY" -m unittest discover -s deployment/tests -v
"$PY" -m pip freeze > "$BUILD_DIR/package/requirements-resolved.txt"
"$PY" -m pip download --only-binary=:all: --dest "$BUILD_DIR/package/wheels" -r "$BUILD_DIR/package/requirements-resolved.txt"
REVISION="$REVISION" "$PY" - "$BUILD_DIR/package" <<'PY'
import json, os, pathlib, platform, sys
pathlib.Path(sys.argv[1], 'RELEASE.json').write_text(json.dumps({
    'revision': os.environ['REVISION'],
    'python': f'{sys.version_info.major}.{sys.version_info.minor}',
    'machine': platform.machine(),
}))
PY
mkdir -p "$OUTPUT_DIR"
tar --exclude=__pycache__ --exclude='*.pyc' -czf "$OUTPUT_DIR/rpg-game.tar.gz" -C "$BUILD_DIR/package" .
echo "Created $OUTPUT_DIR/rpg-game.tar.gz"
