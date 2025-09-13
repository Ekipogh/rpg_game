#!/bin/bash
#
# teamcity-agent-install.sh
# Install and configure a TeamCity agent on Ubuntu/Linux server
# Run with sudo privileges
#

set -e

# Configuration variables
TEAMCITY_URL="${1:-http://localhost:8111}"
AGENT_NAME="${2:-rpg-game-agent}"
AGENT_DIR="${3:-/opt/teamcity-agent}"
AGENT_USER="${4:-teamcity}"
AUTH_TOKEN="${5:-}"

echo "Installing TeamCity agent to $AGENT_DIR connecting to $TEAMCITY_URL as $AGENT_NAME"

# Create teamcity user if it doesn't exist
if ! id "$AGENT_USER" &>/dev/null; then
    echo "Creating user $AGENT_USER"
    useradd -r -s /bin/bash -d "$AGENT_DIR" -m "$AGENT_USER"
fi

# Create agent directory
mkdir -p "$AGENT_DIR"
cd "$AGENT_DIR"

# Download agent from TeamCity server
AGENT_ZIP_URL="$TEAMCITY_URL/update/buildAgent.zip"
echo "Downloading agent from $AGENT_ZIP_URL"

if command -v wget >/dev/null; then
    wget "$AGENT_ZIP_URL" -O buildAgent.zip
elif command -v curl >/dev/null; then
    curl -L "$AGENT_ZIP_URL" -o buildAgent.zip
else
    echo "Error: wget or curl required to download agent"
    exit 1
fi

# Extract agent
echo "Extracting agent to $AGENT_DIR"
unzip -o buildAgent.zip
rm buildAgent.zip

# Configure buildAgent.properties
PROP_FILE="$AGENT_DIR/conf/buildAgent.properties"
echo "Configuring agent properties in $PROP_FILE"

# Backup original if exists
if [ -f "$PROP_FILE" ]; then
    cp "$PROP_FILE" "$PROP_FILE.backup"
fi

# Update configuration
sed -i "s|^name=.*|name=$AGENT_NAME|" "$PROP_FILE"
sed -i "s|^serverUrl=.*|serverUrl=$TEAMCITY_URL|" "$PROP_FILE"

# Add auth token if provided
if [ -n "$AUTH_TOKEN" ]; then
    echo "authorizationToken=$AUTH_TOKEN" >> "$PROP_FILE"
fi

# Set ownership
chown -R "$AGENT_USER:$AGENT_USER" "$AGENT_DIR"

# Create systemd service
SERVICE_FILE="/etc/systemd/system/teamcity-agent.service"
echo "Creating systemd service at $SERVICE_FILE"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=TeamCity Build Agent
After=network.target

[Service]
Type=forking
User=$AGENT_USER
Group=$AGENT_USER
ExecStart=$AGENT_DIR/bin/agent.sh start
ExecStop=$AGENT_DIR/bin/agent.sh stop
PIDFile=$AGENT_DIR/logs/buildAgent.pid
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable teamcity-agent

echo "TeamCity agent installed successfully!"
echo "Start the agent with: sudo systemctl start teamcity-agent"
echo "Check status with: sudo systemctl status teamcity-agent"
echo "Accept the agent in TeamCity UI at $TEAMCITY_URL/agents.html"
