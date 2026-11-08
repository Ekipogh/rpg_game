#!/bin/bash
# sudo bash deployment/setup-ubuntu.sh TEAMCITY_AGENT_USER GAME_HOSTNAME [HTTP_PORT] [APP_PORT]
# Supported baseline: Ubuntu 26.04, with an existing TeamCity agent account.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run this script with sudo.' >&2; exit 1; }
[[ $# -ge 2 && $# -le 4 ]] || { echo "Usage: $0 AGENT_USER GAME_HOSTNAME_OR_IP [HTTP_PORT] [APP_PORT]" >&2; exit 1; }
AGENT_USER="$1"
GAME_HOST="$2"
[[ "$AGENT_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo 'Invalid agent user'; exit 1; }
[[ "$GAME_HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || { echo 'Use a hostname or IPv4 address without scheme/port'; exit 1; }
[[ "$AGENT_USER" != root && "$AGENT_USER" != rpg-game ]] || { echo 'Use a separate non-root agent account'; exit 1; }
id "$AGENT_USER" >/dev/null
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 26.04 ]] || { echo 'This setup supports Ubuntu 26.04 (Python 3.14).'; exit 1; }
RPG_HTTP_PORT=8080
RPG_APP_PORT=8000
if [[ -f /etc/rpg_game/environment ]]; then
    source /etc/rpg_game/environment
fi
RPG_HTTP_PORT="${3:-$RPG_HTTP_PORT}"
RPG_APP_PORT="${4:-$RPG_APP_PORT}"
for port in "$RPG_HTTP_PORT" "$RPG_APP_PORT"; do
    [[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || { echo "Invalid port: $port (use 1-65535, without leading zeros)" >&2; exit 1; }
done
[[ "$RPG_HTTP_PORT" != "$RPG_APP_PORT" ]] || { echo 'HTTP and application ports must differ.' >&2; exit 1; }
# Gunicorn runs without privileges and cannot bind to privileged ports.
(( RPG_APP_PORT >= 1024 )) || { echo 'APP_PORT must be 1024 or greater.' >&2; exit 1; }
export RPG_HTTP_PORT RPG_APP_PORT
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
for file in deploy.py rpg_game.service rpg_game-battle.service rpg_game-healing.service nginx.conf.template; do
    [[ -f "$SOURCE_DIR/$file" ]] || { echo "Missing $SOURCE_DIR/$file"; exit 1; }
done
NGINX_TEMPLATE="$SOURCE_DIR/nginx.conf.template"
if [[ -f "$SOURCE_DIR/nginx-config" ]]; then
    NGINX_TEMPLATE="$SOURCE_DIR/nginx-config"
    echo 'Using custom Nginx template.'
fi
for placeholder in '${RPG_HTTP_PORT}' '${RPG_APP_PORT}'; do
    grep -Fq "$placeholder" "$NGINX_TEMPLATE" || { echo "Nginx template must contain $placeholder" >&2; exit 1; }
done
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3.14 python3.14-venv git curl nginx sudo util-linux ca-certificates gettext-base
if ! id rpg-game >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/rpg_game --shell /usr/sbin/nologin rpg-game
fi
install -d -m 0755 -o root -g root /opt/rpg_game /opt/rpg_game/releases /usr/local/lib/rpg_game
install -d -m 0750 -o rpg-game -g rpg-game /var/lib/rpg_game
install -d -m 0700 -o root -g root /var/backups/rpg_game
install -d -m 0750 -o root -g rpg-game /etc/rpg_game
if [[ ! -e /etc/rpg_game/environment ]]; then
    umask 077
    SECRET="$(python3.14 -c 'import secrets; print(secrets.token_hex(48))')"
    cat > /etc/rpg_game/environment <<EOF
# Shared by systemd and the deploy helper. Keep Bash-compatible KEY=value syntax.
DJANGO_SECRET_KEY='$SECRET'
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,$GAME_HOST
RPG_DATA_DIR=/var/lib/rpg_game
EOF
    unset SECRET
fi
# Replace only port settings; preserve the existing secret and other settings.
sed -i '/^[[:space:]]*\(export[[:space:]]\+\)\?RPG_\(HTTP\|APP\)_PORT=/d' /etc/rpg_game/environment
printf '\nRPG_HTTP_PORT=%s\nRPG_APP_PORT=%s\n' "$RPG_HTTP_PORT" "$RPG_APP_PORT" >> /etc/rpg_game/environment
chown root:rpg-game /etc/rpg_game/environment
chmod 0640 /etc/rpg_game/environment
install -m 0644 "$SOURCE_DIR/deploy.py" /usr/local/lib/rpg_game/deploy.py
cat > /usr/local/sbin/rpg-game-deploy <<'EOF'
#!/bin/sh
exec /usr/bin/python3.14 -I /usr/local/lib/rpg_game/deploy.py "$@"
EOF
chown root:root /usr/local/sbin/rpg-game-deploy
chmod 0755 /usr/local/sbin/rpg-game-deploy
for service in rpg_game rpg_game-battle rpg_game-healing; do
    install -m 0644 "$SOURCE_DIR/$service.service" "/etc/systemd/system/$service.service"
done
# Install sudoers atomically only after syntax validation.
SUDO_FILE="$(mktemp)"
trap 'rm -f -- "$SUDO_FILE"' EXIT
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/rpg-game-deploy *\n' "$AGENT_USER" > "$SUDO_FILE"
visudo -cf "$SUDO_FILE"
install -m 0440 "$SUDO_FILE" /etc/sudoers.d/rpg-game-deploy
# Restrict substitution to our ports so Nginx's $host/$scheme variables survive.
envsubst '${RPG_HTTP_PORT} ${RPG_APP_PORT}' < "$NGINX_TEMPLATE" > /etc/nginx/sites-available/rpg_game
ln -sfn /etc/nginx/sites-available/rpg_game /etc/nginx/sites-enabled/rpg_game
nginx -t
systemctl daemon-reload
# verify also checks ExecStart executables, which do not exist before release 1.
if [[ -x /opt/rpg_game/current/.venv/bin/gunicorn ]]; then
    systemd-analyze verify /etc/systemd/system/rpg_game{,-battle,-healing}.service
fi
systemctl enable rpg_game rpg_game-battle rpg_game-healing
systemctl enable --now nginx
systemctl reload nginx
echo "Setup complete. Game URL after deployment: http://$GAME_HOST:$RPG_HTTP_PORT/"
echo "Gunicorn and deployment readiness checks use 127.0.0.1:$RPG_APP_PORT."
echo 'Game data and non-port environment settings were preserved; application services were not started/restarted.'
echo 'If changing ports on a running installation, restart rpg_game or deploy a release to apply the new backend port.'
echo 'In TeamCity add agent parameter: rpg.deploy.target=local-ubuntu'
echo 'Run the Deploy build configuration to build, test, and install the first release.'
