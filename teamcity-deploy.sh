#!/bin/bash
#
# teamcity-deploy.sh
# Deployment script for rpg_game on Ubuntu server
# Run from TeamCity agent or manually for deployment
#

set -e

# Configuration
APP_DIR="${1:-/var/www/rpg_game}"
VENV_PATH="${2:-$APP_DIR/.venv}"
SERVICE_NAME="${3:-rpg_game}"
APP_USER="${4:-www-data}"
RUN_MIGRATIONS="${5:-true}"
RUN_COLLECTSTATIC="${6:-false}"

echo "Deploying rpg_game from $APP_DIR"
cd "$APP_DIR"

# Optional: pull latest changes if this is a git working copy
if [ -d ".git" ]; then
    echo "Updating git working copy"
    git fetch origin
    git reset --hard HEAD
    git clean -fd
    # Note: TeamCity agent typically checks out fresh, so this may not be needed
fi

# Activate virtual environment
if [ -f "$VENV_PATH/bin/activate" ]; then
    echo "Activating virtual environment at $VENV_PATH"
    source "$VENV_PATH/bin/activate"
else
    echo "Warning: Virtual environment not found at $VENV_PATH"
    echo "Proceeding with system Python"
fi

# Install/update dependencies
echo "Installing Python dependencies"
pip install -r requirements.txt

# Run migrations if requested
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations"
    python manage.py migrate --noinput
fi

# Collect static files if requested
if [ "$RUN_COLLECTSTATIC" = "true" ]; then
    echo "Collecting static files"
    python manage.py collectstatic --noinput
fi

# Set proper ownership
echo "Setting file ownership to $APP_USER"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# Restart the application service
echo "Restarting service: $SERVICE_NAME"
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Stopping $SERVICE_NAME"
    systemctl stop "$SERVICE_NAME"
    sleep 2
fi

echo "Starting $SERVICE_NAME"
systemctl start "$SERVICE_NAME"

# Check service status
echo "Checking service status"
systemctl status "$SERVICE_NAME" --no-pager

echo "Deployment completed successfully!"

# Optional: run a health check
if command -v curl >/dev/null; then
    echo "Running health check..."
    sleep 3
    if curl -f -s http://localhost:8000/health/ >/dev/null 2>&1; then
        echo "✓ Health check passed"
    else
        echo "⚠ Health check failed - service may still be starting"
    fi
fi
