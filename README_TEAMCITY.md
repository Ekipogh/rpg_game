TeamCity deployment guide for rpg_game (Ubuntu)

Overview
--------
This document shows a minimal setup to use TeamCity to deploy `rpg_game` with an agent on Ubuntu/Linux server.

Steps (high-level)
-------------------
1. Install TeamCity server somewhere reachable (example: http://ci.example.com:8111).
2. On the target Ubuntu server, run `teamcity-agent-install.sh` to download and register an agent with your TeamCity server.
   - Run with sudo: `sudo ./teamcity-agent-install.sh http://your-teamcity:8111 rpg-game-agent`
3. Import `.teamcity/settings.kts` into TeamCity (Admin -> Projects -> VCS Roots / Kotlin DSL) or copy the config as a starting point.
4. Configure a build configuration that checks out the repository and runs `teamcity-deploy.sh` on the agent.

Security and secrets
--------------------
- Do not store secrets in VCS. Use TeamCity project parameters or a secret manager.
- Use an SSH key or a TeamCity Token for connecting to GitHub; configure this in the TeamCity UI under VCS Roots.

Agent notes (Ubuntu)
--------------------
- The example scripts assume Ubuntu with systemd and a venv at `/var/www/rpg_game/.venv`.
- The agent runs as the `teamcity` user; ensure this user has sudo access or permissions to restart the application service.
- The application should run as a systemd service named `rpg_game`.

Application service setup
-------------------------
Create a systemd service for your Django app at `/etc/systemd/system/rpg_game.service`:

```ini
[Unit]
Description=RPG Game Django Application
After=network.target

[Service]
Type=exec
User=www-data
Group=www-data
WorkingDirectory=/var/www/rpg_game
Environment=DJANGO_SETTINGS_MODULE=game.settings
ExecStart=/var/www/rpg_game/.venv/bin/python manage.py runserver 0.0.0.0:8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable with: `sudo systemctl enable rpg_game && sudo systemctl start rpg_game`

Customizing build steps
-----------------------
- The Kotlin DSL file `.teamcity/settings.kts` includes Ubuntu-specific steps: install deps, migrate, collectstatic, restart systemd service.
- Adapt the commands for your environment (paths, service names, or container commands if using Docker).

File permissions
---------------
- Ensure the TeamCity agent user can read the application directory and restart the service.
- Add the agent user to sudoers for service control: `teamcity ALL=(ALL) NOPASSWD: /bin/systemctl restart rpg_game, /bin/systemctl start rpg_game, /bin/systemctl stop rpg_game`

Troubleshooting
---------------
- Agent doesn't appear: check TeamCity UI -> Agents and verify the agent's `conf/buildAgent.properties` has correct `serverUrl`.
- Registration blocked: accept the agent in TeamCity as an admin.
- Service restart fails: check sudo permissions and systemd service configuration.
- Permissions: ensure the app directory is owned by the correct user (www-data) and the agent can write to logs.

Next steps
----------
- I can: (a) add a sample systemd service file, (b) add Nginx reverse proxy configuration, or (c) help you set up GitHub -> TeamCity webhooks or GitHub App integration.
