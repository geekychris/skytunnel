#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# tunnelctl Agent Setup Wizard
# ============================================================================
# Interactive installer for the Starlink-side tunnel agent.
# Walks through: dependencies, SSH keys, endpoint config, tunnel definitions,
# Telegram setup, and service installation.
# ============================================================================

CONFIG_PATH="config.yaml"
ENV_PATH=".env"

# --- Colors and helpers ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
header()  { echo -e "\n${BOLD}${CYAN}═══ $* ═══${NC}\n"; }

ask() {
    local prompt="$1" default="${2:-}"
    if [[ -n "$default" ]]; then
        read -rp "$(echo -e "${BOLD}$prompt${NC} [$default]: ")" answer
        echo "${answer:-$default}"
    else
        read -rp "$(echo -e "${BOLD}$prompt${NC}: ")" answer
        echo "$answer"
    fi
}

ask_yn() {
    local prompt="$1" default="${2:-y}"
    while true; do
        read -rp "$(echo -e "${BOLD}$prompt${NC} [${default}]: ")" answer
        answer="${answer:-$default}"
        case "${answer,,}" in
            y|yes) return 0 ;;
            n|no)  return 1 ;;
            *) echo "Please answer y or n." ;;
        esac
    done
}

# ============================================================================
echo ""
echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║       tunnelctl Agent Setup Wizard           ║"
echo "  ║                                              ║"
echo "  ║  This wizard will configure the tunnel agent ║"
echo "  ║  for your Starlink-side machine.             ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# ============================================================================
header "Step 1/7: System Check"
# ============================================================================

# Check Python
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]]; then
        success "Python $PY_VERSION found"
    else
        error "Python 3.11+ required, found $PY_VERSION"
        echo "  Install from https://www.python.org/downloads/ or use Docker."
        exit 1
    fi
else
    error "Python 3 not found"
    echo "  Install from https://www.python.org/downloads/ or use Docker."
    exit 1
fi

# Check SSH
if command -v ssh &>/dev/null; then
    success "SSH client found"
else
    error "SSH client not found. Install OpenSSH."
    exit 1
fi

# Detect OS
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
    Linux*)  OS_TYPE="linux" ;;
    Darwin*) OS_TYPE="macos" ;;
    *)       OS_TYPE="other" ;;
esac
info "Detected: $OS ($ARCH)"

# ============================================================================
header "Step 2/7: Install tunnelctl"
# ============================================================================

if command -v tunnelctl &>/dev/null; then
    success "tunnelctl is already installed"
    if ask_yn "Reinstall/upgrade?"; then
        pip install -e . 2>&1 | tail -3
        success "Reinstalled"
    fi
else
    info "Installing tunnelctl..."
    pip install -e . 2>&1 | tail -3
    success "Installed"
fi

# ============================================================================
header "Step 3/7: SSH Key Setup"
# ============================================================================

KEY_NAME=$(ask "SSH key name" "tunnel_key")
KEY_PATH="$HOME/.ssh/$KEY_NAME"

if [[ -f "$KEY_PATH" ]]; then
    success "Key already exists at $KEY_PATH"
    if ask_yn "Generate a new key instead?" "n"; then
        BACKUP="${KEY_PATH}.backup.$(date +%s)"
        mv "$KEY_PATH" "$BACKUP"
        mv "${KEY_PATH}.pub" "${BACKUP}.pub"
        warn "Old key backed up to $BACKUP"
    else
        info "Using existing key"
    fi
fi

if [[ ! -f "$KEY_PATH" ]]; then
    info "Generating ed25519 SSH key..."
    ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -C "tunnelctl-agent" -q
    chmod 600 "$KEY_PATH"
    success "Key generated at $KEY_PATH"
fi

echo ""
echo -e "  ${BOLD}Public key to add to endpoint servers:${NC}"
echo -e "  ${CYAN}$(cat "${KEY_PATH}.pub")${NC}"
echo ""
echo "  Copy this key to each endpoint server's authorized_keys."
echo "  The endpoint wizard (wizard-endpoint.sh) can do this for you."
echo ""

# ============================================================================
header "Step 4/7: Endpoint Configuration"
# ============================================================================

ENDPOINTS=()
ENDPOINT_YAML=""
EP_INDEX=0

while true; do
    EP_INDEX=$((EP_INDEX + 1))
    echo -e "${BOLD}--- Endpoint #$EP_INDEX ---${NC}"

    EP_NAME=$(ask "Endpoint name (e.g. home-server, cloud-vps)")
    EP_HOST=$(ask "Hostname or IP")
    EP_PORT=$(ask "SSH port" "22")
    EP_USER=$(ask "SSH username" "tunnel")
    EP_KEYFILE=$(ask "SSH key file" "$KEY_PATH")

    PROXY_TYPE=$(ask "Reverse proxy type (nginx/caddy)" "nginx")
    HTTP_DOMAIN=$(ask "Wildcard domain (e.g. *.home.example.com)" "")

    ENDPOINTS+=("$EP_NAME")

    ENDPOINT_YAML+="
  - name: $EP_NAME
    host: $EP_HOST
    port: $EP_PORT
    user: $EP_USER
    key_file: $EP_KEYFILE
    proxy:
      type: $PROXY_TYPE
      http_domain: \"$HTTP_DOMAIN\"
      ssl: true
      config_path: /etc/${PROXY_TYPE}/conf.d/tunnelctl.conf
      reload_command: \"${PROXY_TYPE} -s reload\""

    # Test connectivity
    echo ""
    if ask_yn "Test SSH connectivity to $EP_NAME now?"; then
        echo -n "  Connecting... "
        if ssh -i "$EP_KEYFILE" -o BatchMode=yes -o ConnectTimeout=10 \
           -o StrictHostKeyChecking=no "$EP_USER@$EP_HOST" -p "$EP_PORT" \
           "echo ok" 2>/dev/null; then
            success "Connection successful"
        else
            warn "Connection failed. You may need to:"
            echo "    1. Add the public key to $EP_USER@$EP_HOST:~/.ssh/authorized_keys"
            echo "    2. Ensure sshd is running on $EP_HOST:$EP_PORT"
            echo "    3. Check firewall rules"
        fi
    fi

    echo ""
    if ! ask_yn "Add another endpoint?"; then
        break
    fi
    echo ""
done

# ============================================================================
header "Step 5/7: Tunnel Configuration"
# ============================================================================

TUNNEL_YAML=""
T_INDEX=0

echo "Now define the services on your LAN that you want to expose."
echo "You can always add more later via the CLI, web UI, or Telegram."
echo ""

while true; do
    T_INDEX=$((T_INDEX + 1))
    echo -e "${BOLD}--- Tunnel #$T_INDEX ---${NC}"

    T_NAME=$(ask "Tunnel name (e.g. nas-web, pi-ssh)")
    T_INT_HOST=$(ask "Internal device IP (e.g. 192.168.1.10)")
    T_INT_PORT=$(ask "Internal port (e.g. 80, 22, 8080)")
    T_REM_PORT=$(ask "Remote port to expose on endpoint(s)")

    echo "  Protocol types:"
    echo "    tcp  - Raw TCP forwarding (SSH, databases, etc.)"
    echo "    http - HTTP service (gets subdomain routing via reverse proxy)"
    T_PROTOCOL=$(ask "Protocol" "tcp")

    T_SUBDOMAIN=""
    if [[ "$T_PROTOCOL" == "http" ]]; then
        T_SUBDOMAIN=$(ask "Subdomain (e.g. 'nas' -> nas.yourdomain.com)" "")
    fi

    # Select endpoints
    if [[ ${#ENDPOINTS[@]} -eq 1 ]]; then
        T_ENDPOINTS="[${ENDPOINTS[0]}]"
        info "Using endpoint: ${ENDPOINTS[0]}"
    else
        echo "  Available endpoints: ${ENDPOINTS[*]}"
        echo "  Enter comma-separated names, or 'all' for all endpoints."
        T_EP_INPUT=$(ask "Endpoints" "all")
        if [[ "$T_EP_INPUT" == "all" || -z "$T_EP_INPUT" ]]; then
            T_ENDPOINTS="[]"
        else
            T_ENDPOINTS="[$(echo "$T_EP_INPUT" | sed 's/,/, /g')]"
        fi
    fi

    TUNNEL_YAML+="
  - name: $T_NAME
    internal_host: $T_INT_HOST
    internal_port: $T_INT_PORT
    remote_port: $T_REM_PORT
    protocol: $T_PROTOCOL
    endpoints: $T_ENDPOINTS"

    if [[ -n "$T_SUBDOMAIN" ]]; then
        TUNNEL_YAML+="
    subdomain: $T_SUBDOMAIN"
    fi

    echo ""
    if ! ask_yn "Add another tunnel?"; then
        break
    fi
    echo ""
done

# ============================================================================
header "Step 6/7: Telegram Integration"
# ============================================================================

TELEGRAM_YAML="
telegram:
  enabled: false"

if ask_yn "Set up Telegram bot for remote management and alerts?"; then
    echo ""
    echo "  You need a bot token from @BotFather and your chat ID."
    echo "  See README.md for detailed instructions."
    echo ""

    TG_TOKEN=$(ask "Bot token (from @BotFather)")
    TG_CHATID=$(ask "Chat ID (your Telegram user ID)")

    TELEGRAM_YAML="
telegram:
  enabled: true
  bot_token: \"\${TELEGRAM_BOT_TOKEN}\"
  chat_id: \"\${TELEGRAM_CHAT_ID}\"
  alert_on_disconnect: true
  alert_on_reconnect: true"

    # Write .env file
    cat > "$ENV_PATH" << EOF
TELEGRAM_BOT_TOKEN=$TG_TOKEN
TELEGRAM_CHAT_ID=$TG_CHATID
EOF
    chmod 600 "$ENV_PATH"
    success "Saved Telegram credentials to $ENV_PATH"
fi

# ============================================================================
header "Step 7/7: Generate Configuration & Install Service"
# ============================================================================

# --- Write config.yaml ---
API_PORT=$(ask "Web dashboard / API port" "8080")
API_HOST=$(ask "API bind address" "0.0.0.0")
LOG_LEVEL=$(ask "Log level (DEBUG/INFO/WARNING/ERROR)" "INFO")

cat > "$CONFIG_PATH" << EOF
global:
  reconnect_interval: 30
  health_check_interval: 60
  health_check_timeout: 10
  log_level: $LOG_LEVEL
  state_db: ./tunnelctl.db
  api_port: $API_PORT
  api_host: $API_HOST
$TELEGRAM_YAML

endpoints:$ENDPOINT_YAML

tunnels:$TUNNEL_YAML
EOF

success "Configuration written to $CONFIG_PATH"

# --- Install as system service ---
echo ""
if ask_yn "Install tunnelctl as a system service (auto-start on boot)?"; then
    TUNNELCTL_BIN=$(which tunnelctl 2>/dev/null || echo "$(pwd)/.venv/bin/tunnelctl")
    WORK_DIR=$(pwd)

    if [[ "$OS_TYPE" == "linux" ]]; then
        # --- Systemd ---
        SERVICE_FILE="/etc/systemd/system/tunnelctl-agent.service"
        info "Creating systemd service..."

        ENV_LINE=""
        if [[ -f "$ENV_PATH" ]]; then
            ENV_LINE="EnvironmentFile=$WORK_DIR/$ENV_PATH"
        fi

        sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=tunnelctl tunnel agent
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=$USER
WorkingDirectory=$WORK_DIR
ExecStart=$TUNNELCTL_BIN agent -c $WORK_DIR/$CONFIG_PATH
Restart=always
RestartSec=10
$ENV_LINE

[Install]
WantedBy=multi-user.target
EOF

        sudo systemctl daemon-reload
        sudo systemctl enable tunnelctl-agent
        success "Systemd service installed: tunnelctl-agent"

        if ask_yn "Start the agent now?"; then
            sudo systemctl start tunnelctl-agent
            sleep 2
            if systemctl is-active --quiet tunnelctl-agent; then
                success "Agent is running"
            else
                warn "Agent may have failed to start. Check: sudo journalctl -u tunnelctl-agent -f"
            fi
        fi

    elif [[ "$OS_TYPE" == "macos" ]]; then
        # --- launchd ---
        PLIST_PATH="$HOME/Library/LaunchAgents/com.tunnelctl.agent.plist"
        info "Creating launchd plist..."

        mkdir -p "$HOME/Library/LaunchAgents"

        # Build environment variables section
        ENV_DICT=""
        if [[ -f "$ENV_PATH" ]]; then
            ENV_DICT="    <key>EnvironmentVariables</key>
    <dict>"
            while IFS='=' read -r key value; do
                [[ -z "$key" || "$key" == \#* ]] && continue
                ENV_DICT+="
        <key>$key</key><string>$value</string>"
            done < "$ENV_PATH"
            ENV_DICT+="
    </dict>"
        fi

        cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.tunnelctl.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$TUNNELCTL_BIN</string>
        <string>agent</string>
        <string>-c</string>
        <string>$WORK_DIR/$CONFIG_PATH</string>
    </array>
    <key>WorkingDirectory</key><string>$WORK_DIR</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/tmp/tunnelctl-agent.log</string>
    <key>StandardErrorPath</key><string>/tmp/tunnelctl-agent.log</string>
$ENV_DICT
</dict>
</plist>
EOF

        success "launchd plist written to $PLIST_PATH"

        if ask_yn "Start the agent now?"; then
            launchctl load "$PLIST_PATH" 2>/dev/null || true
            sleep 2
            if launchctl list | grep -q com.tunnelctl.agent; then
                success "Agent is running"
            else
                warn "Agent may have failed. Check: tail -f /tmp/tunnelctl-agent.log"
            fi
        fi
    fi
else
    echo ""
    echo "  To start the agent manually:"
    if [[ -f "$ENV_PATH" ]]; then
        echo "    source $ENV_PATH && export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID"
    fi
    echo "    tunnelctl agent -c $CONFIG_PATH"
fi

# ============================================================================
echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║          Setup Complete!                     ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo "  Config:     $CONFIG_PATH"
[[ -f "$ENV_PATH" ]] && echo "  Env:        $ENV_PATH"
echo "  SSH key:    $KEY_PATH"
echo "  Dashboard:  http://localhost:$API_PORT"
echo ""
echo "  Useful commands:"
echo "    tunnelctl status               # Check tunnel status"
echo "    tunnelctl tunnels list         # List tunnels"
echo "    tunnelctl logs                 # View logs"
echo "    tunnelctl check -c $CONFIG_PATH  # Test SSH connectivity"
echo ""
echo "  Next: Run wizard-endpoint.sh on each public endpoint server."
echo ""
