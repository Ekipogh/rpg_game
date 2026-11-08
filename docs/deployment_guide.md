# Local Ubuntu deployment guide

The deployment target is **Ubuntu 26.04, Python 3.14**, with an existing TeamCity
agent. The build and deployment configurations use the same marked agent host,
so downloaded wheels match the target architecture and operating system.

Ubuntu 26.04 supplies [Python 3.14](https://packages.ubuntu.com/resolute/python3).
Build new release artifacts on the Ubuntu 26.04 agent after upgrading the host;
Python 3.12 artifacts and old virtualenvs are not compatible with this deployment
target. Preserve database backups and rebuild any older revision you need to
restore using Python 3.14 rather than reusing its old virtualenv.

## First-time machine setup

Commit and push these deployment changes before building: release packaging uses
`git archive HEAD` and deliberately excludes uncommitted files.

Create a ./deployment/nginx-config file with your Nginx configuration for the game,
or use default, defined in the script.

On the Ubuntu machine, check out the repository and run:

```bash
sudo bash deployment/setup-ubuntu.sh teamcity 192.168.1.50
```

Replace `teamcity` with the Linux account that actually runs your TeamCity agent.
Replace the IP with the address or hostname you will use to open the game. Supply
no URL scheme or port. The account must already exist and must be separate from
root and the application account. If the agent is not installed yet, install and
authorize it with your TeamCity server first. Setup does not install a TeamCity
server, agent, or Java runtime.

The setup script installs Python/venv, Git, curl, Nginx, sudo, and util-linux. It
creates the application account, generates a random Django secret, installs a
root-owned deployment helper, enables three systemd services, and configures
Nginx on port 8080. It starts/reloads Nginx but leaves application services alone
until the first deployment. Existing environment and game data are preserved on
reruns. Existing service definitions and the RPG Nginx site are replaced; back up
any custom versions before rerunning setup. Port 8000 must be available for
Gunicorn, and port 8080 must be available for this Nginx site.

The resulting layout is:

```text
/opt/rpg_game/releases/<timestamp>/   code, virtualenv, wheels, staticfiles
/opt/rpg_game/current                symlink to the active release
/var/lib/rpg_game/                   SQLite database and daemon state
/etc/rpg_game/environment            shared environment and secret
/var/backups/rpg_game/<timestamp>/    data snapshot and previous release pointer
/usr/local/sbin/rpg-game-deploy       restricted deployment entry point
/usr/local/lib/rpg_game/deploy.py     root-owned deployment implementation
```

The game will be available at `http://192.168.1.50:8080/` after deployment. Setup
does not change the firewall. If UFW is enabled, allow port 8080 only from your
trusted LAN as appropriate. This setup uses HTTP for local use; configure TLS and
Django's HTTPS/cookie settings before exposing it beyond the trusted local network.

## TeamCity configuration

1. In the target agent's custom configuration parameters, add
   `rpg.deploy.target=local-ubuntu`. Alternatively put that line in the agent's
   `conf/buildAgent.properties` and restart the agent. Mark only the intended
   Ubuntu host with this value.
2. Import `.teamcity/settings.kts` as versioned settings. Configure GitHub access
   in the TeamCity VCS root if authentication is needed. The repository defaults
   to `main`; adjust the URL/branch for your repository if different.
3. Run **Deploy game to local Ubuntu**. Its snapshot dependency runs or reuses
   the matching successful **Build and test release**, and its artifact dependency
   selects that build's artifact from the same chain. Deployment does not check
   out or install an unrelated working tree.
4. Verify the site and logs after the first run. The VCS deployment trigger is
   initially disabled. Enable it in versioned settings (`enabled = true` on the
   Deploy trigger) if pushes to `main` should automatically build and deploy.

The build creates a clean venv, installs production dependencies, runs Django
checks/migration-drift detection and tests plus deployment-helper tests, freezes
resolved versions, downloads their wheels, and publishes `rpg-game.tar.gz`.
Builds need access to the Python package index. Deployment installs those exact
resolved packages from the artifact with `--no-index`; it does not resolve new
versions or need package-index access. Dependency resolution can change between
builds because the base requirements are not fully pinned; every resulting
artifact records and retains its own tested versions. Gunicorn is explicitly
included in `requirements-production.txt`.

The TeamCity deployment configuration permits one running deployment; the helper
also takes a host-level file lock to block overlapping manual/CI deployments.
Do not run untrusted pull-request builds on an agent authorized to deploy: that
agent can install application code that can access the game's data and secret.
The sudo rule grants access to the fixed helper, not arbitrary root shell or
systemctl commands. Application installation and management commands run as the
unprivileged `rpg-game` user.

## Deployment sequence

The helper copies the artifact into root-only staging, rejects unsafe archive
paths/links/devices and incompatible Python/architecture manifests, and creates a
new release. It prepares the venv, checks dependencies/application configuration,
and collects static files before stopping the existing game.

It then stops web, battle, and healing services, copies persistent data to a
protected backup, runs migrations, switches `current`, and starts all three
services. On a new database only, it creates starter hero classes and battle
content. Existing installations retain customized classes and encounter content.

Deployment succeeds only when `/health/` responds with the expected Git revision
and all three services are active after a short startup interval. The endpoint
also performs a database query. This checks startup/readiness, not a full gameplay
session. A failed deployment returns nonzero to TeamCity.

If deployment fails during preparation, the running release is left alone. If it
fails after service shutdown, services remain stopped and a backup/recovery
instruction is printed. The helper does not start old code against a database
whose migrations may have partially changed. Keep all other database writers
stopped during deployment; only the three supplied services are managed.

## Bring an existing database across

Do this **before the first deployment**, otherwise a new empty game is initialized.
Stop the old web service and every old daemon/scheduled task that writes to the
old database. Keep a separate backup of that installation. Then, for example:

```bash
sudo systemctl stop rpg_game rpg_game-battle rpg_game-healing
sudo python3.14 - <<'PY'
import sqlite3
with sqlite3.connect('/var/www/rpg_game/db.sqlite3') as source:
    with sqlite3.connect('/var/lib/rpg_game/db.sqlite3') as destination:
        source.backup(destination)
PY
sudo chown rpg-game:rpg-game /var/lib/rpg_game/db.sqlite3
sudo chmod 640 /var/lib/rpg_game/db.sqlite3
```

Use your actual old path and verify it exists first: SQLite creates a database if
the path is missing. Copy existing `healing_state.json`, `daemon_commands.json`,
and `daemon_status.json` into `/var/lib/rpg_game/` if present, with ownership
`rpg-game:rpg-game` and mode 0640. Copy any other persistent data you maintain.
Review `/etc/rpg_game/environment`; preserve the old Django secret if existing
sessions need to survive. Do not keep old daemons pointed at the imported data.

## Environment and application administration

Edit `/etc/rpg_game/environment` as root. Settings consume:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Stable generated secret; preserve during normal releases. |
| `DJANGO_DEBUG` | Setup sets `False`. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames/IPs, including localhost and 127.0.0.1 for readiness checks. Do not include ports or URL schemes. |
| `RPG_DATA_DIR` | Database and daemon-state directory; setup uses `/var/lib/rpg_game`. Defaults to the project directory for existing development workflows. |

The file is read by systemd and Bash, so use Bash-compatible `KEY=value` syntax
and quote values containing shell metacharacters. `.env` is not loaded
implicitly; `DATABASE_URL` is not used. After changing runtime environment values,
restart all application services. Changing only this file does not require
`daemon-reload`; changing unit files does.

To create the first administrator after deployment:

```bash
sudo -u rpg-game bash -c 'set -a; source /etc/rpg_game/environment; set +a; cd /opt/rpg_game/current; exec .venv/bin/python manage.py createsuperuser'
```

Use the same wrapper for other management commands such as `check --deploy` and
`showmigrations`. Review deployment warnings against your exposure/TLS plan. See
[battle daemon operations](battle_daemon.md) for encounter configuration and
paused-fight recovery. The supplied healing service runs passive recovery.

## Verification and logs

```bash
sudo systemctl status rpg_game rpg_game-battle rpg_game-healing --no-pager
sudo journalctl -u rpg_game -u rpg_game-battle -u rpg_game-healing -n 100 --no-pager
curl --fail http://127.0.0.1:8000/health/
curl --fail http://192.168.1.50:8080/health/
cat /opt/rpg_game/current/RELEASE.json
```

Verify styles/images in the browser, log into admin, select/create a hero, and
confirm a battle advances. Nginx serves `/static/` from the active release's
`staticfiles`; Gunicorn only listens on loopback. No public media upload route is
configured by this setup.

## Manual build/deploy and updating deployment tools

From a committed checkout on the configured Ubuntu machine:

```bash
bash deployment/build-release.sh
sudo -n /usr/local/sbin/rpg-game-deploy --artifact "$PWD/dist/rpg-game.tar.gz"
```

Application releases do not overwrite the privileged helper or systemd units.
When changing deployment infrastructure, rerun `setup-ubuntu.sh` from a reviewed
checkout with sudo, then deploy the application. Setup preserves the environment
file, so a different hostname argument on a later run does not update existing
allowed hosts; edit the environment explicitly.

## Recovery and retention

On a failure after a successful previous release, deployment prints:

```bash
sudo rpg-game-deploy --restore 20261108T120000123456Z
```

Use the actual backup ID from the log. Restore stops the services, backs up the
current data again, restores the chosen data snapshot, switches to the recorded
previous release, and verifies startup. **Writes since the selected backup are
reverted.** Run restores only after deciding to discard those later writes.
A first-install backup has no previous release; fix the error and redeploy. If a
partially initialized database needs fresh starter content, run the documented
setup management commands explicitly after fixing migrations.

Environment secrets are not part of deployment snapshots. Back up
`/etc/rpg_game/` separately and keep the corresponding secret available. Releases
and backups are retained until an operator removes them; monitor disk space.
Do not delete the active release or releases referenced by backups you intend to
restore. Restore assumes the original operating system/Python 3.14 remains
compatible with the retained virtualenv.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| No compatible TeamCity agent | Check the custom `rpg.deploy.target` value and Linux agent requirement. |
| Sudo asks for a password/fails | Verify setup used the actual agent account and `/etc/sudoers.d/rpg-game-deploy` exists. |
| Wrong architecture or Python | Build on the marked Ubuntu 26.04/Python 3.14 host. |
| Artifact build ignores edits | Commit/push them: packaging intentionally uses `HEAD`. |
| HTTP 400 | Add the requested hostname/IP to `DJANGO_ALLOWED_HOSTS` and restart services. |
| Readiness fails | Inspect all three journals, port 8000 conflicts, migrations, and the release revision. |
| Static files fail | Check Nginx configuration, collectstatic output, and read permissions under the active release. |
| SQLite locked/read-only | Stop stale writers and check data-directory ownership; do not delete SQLite journals to clear a lock. |
| First deploy fails on database | Check imported database permissions and migration compatibility; inspect the preserved snapshot. |

## Validation limits

Local automated checks cover Django behavior, archive rejection, data backup,
migration-failure shutdown, first-install seeding, and restoring a matching code
and database pair. Shell syntax is checked separately. Ubuntu package installation,
systemd/Nginx execution, offline wheel installation, and TeamCity DSL import must
still be verified on the actual Ubuntu machine; they cannot be exercised by the
Windows test run. Automatic deployment stays disabled until that supervised run.

TeamCity's dependency model is described in the official
[artifact dependency documentation](https://www.jetbrains.com/help/teamcity/artifact-dependencies.html).
