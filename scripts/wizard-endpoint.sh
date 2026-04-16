#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# tunnelctl Endpoint Setup Wizard
# ============================================================================
# Interactive installer for the public-facing endpoint server.
# Walks through: dependencies, tunnel user, SSH keys, reverse proxy,
# tunnelctl config, firewall, and service installation.
# ============================================================================

CONFIG_PATH="config.yaml"

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
echo "  ║     tunnelctl Endpoint Setup Wizard          ║"
echo "  ║                                              ║"
echo "  ║  This wizard configures a public-facing      ║"
echo "  ║  server to receive tunnels from the agent.   ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# ============================================================================
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
    Linux*)  OS_TYPE="linux" ;;
    Darwin*) OS_TYPE="macos" ;;
    *)       OS_TYPE="other" ;;
esac
info "Detected: $OS ($ARCH)"

# ============================================================================
header "Step 1/7: System Check"
# ============================================================================

# Check Python
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]]; then
        success "Python $PY_VERSION"
    else
        error "Python 3.11+ required, found $PY_VERSION"
        exit 1
    fi
else
    error "Python 3 not found"
    exit 1
fi

# Check sshd
if pgrep -x sshd >/dev/null 2>&1 || systemctl is-active --quiet sshd 2>/dev/null || systemctl is-active --quiet ssh 2>/dev/null; then
    success "SSH server is running"
else
    warn "SSH server does not appear to be running"
    echo "  Start it: sudo systemctl start sshd (or ssh)"
fi

info "Installing tunnelctl..."
pip install -e . 2>&1 | tail -3
success "tunnelctl installed"

# ============================================================================
header "Step 2/7: Tunnel User Setup"
# ============================================================================

TUNNEL_USER=$(ask "Username for tunnel connections" "tunnel")

if id "$TUNNEL_USER" &>/dev/null; then
    success "User '$TUNNEL_USER' already exists"
else
    if ask_yn "Create user '$TUNNEL_USER'?"; then
        if [[ "$OS_TYPE" == "linux" ]]; then
            sudo useradd -m -s /bin/bash "$TUNNEL_USER"
        elif [[ "$OS_TYPE" == "macos" ]]; then
            # macOS user creation
            LAST_ID=$(dscl . -list /Users UniqueID | awk '{print $2}' | sort -n | tail -1)
            NEW_ID=$((LAST_ID + 1))
            sudo dscl . -create "/Users/$TUNNEL_USER"
            sudo dscl . -create "/Users/$TUNNEL_USER" UserShell /bin/bash
            sudo dscl . -create "/Users/$TUNNEL_USER" UniqueID "$NEW_ID"
            sudo dscl . -create "/Users/$TUNNEL_USER" PrimaryGroupID 20
            sudo dscl . -create "/Users/$TUNNEL_USER" NFSHomeDirectory "/Users/$TUNNEL_USER"
            sudo mkdir -p "/Users/$TUNNEL_USER"
            sudo chown "$TUNNEL_USER":staff "/Users/$TUNNEL_USER"
        fi
        success "User '$TUNNEL_USER' created"
    fi
fi

# ============================================================================
header "Step 3/7: SSH Key Authorization"
# ============================================================================

TUNNEL_HOME=$(eval echo "~$TUNNEL_USER")
AUTH_KEYS="$TUNNEL_HOME/.ssh/authorized_keys"

echo "The agent's public key needs to be added to $AUTH_KEYS."
echo ""
echo "You can either:"
echo "  1) Paste the agent's public key now"
echo "  2) Read from a file"
echo "  3) Skip (add it later manually)"
echo ""

KEY_CHOICE=$(ask "Choose (1/2/3)" "1")

case "$KEY_CHOICE" in
    1)
        echo "Paste the agent's public key (from the agent machine's ~/.ssh/tunnel_key.pub):"
        read -r AGENT_PUB_KEY
        ;;
    2)
        KEY_FILE=$(ask "Path to public key file")
        AGENT_PUB_KEY=$(cat "$KEY_FILE")
        ;;
    3)
        AGENT_PUB_KEY=""
        warn "Skipping. Remember to add the key manually before starting the agent."
        ;;
esac

if [[ -n "$AGENT_PUB_KEY" ]]; then
    sudo mkdir -p "$TUNNEL_HOME/.ssh"
    echo "$AGENT_PUB_KEY" | sudo tee -a "$AUTH_KEYS" > /dev/null
    sudo chmod 700 "$TUNNEL_HOME/.ssh"
    sudo chmod 600 "$AUTH_KEYS"
    sudo chown -R "$TUNNEL_USER":"$(id -gn $TUNNEL_USER 2>/dev/null || echo staff)" "$TUNNEL_HOME/.ssh"
    success "Public key added to $AUTH_KEYS"

    # Optionally restrict to port forwarding only
    if ask_yn "Restrict this key to port-forwarding only (more secure)?"; then
        # Replace the last line (the key we just added) with restricted version
        sudo sed -i.bak "s|^${AGENT_PUB_KEY}|restrict,port-forwarding ${AGENT_PUB_KEY}|" "$AUTH_KEYS" 2>/dev/null || \
        sudo sed -i '' "s|^${AGENT_PUB_KEY}|restrict,port-forwarding ${AGENT_PUB_KEY}|" "$AUTH_KEYS"
        success "Key restricted to port-forwarding only"
    fi
fi

# ============================================================================
header "Step 4/7: SSH Server Configuration"
# ============================================================================

SSHD_CONFIG="/etc/ssh/sshd_config"

# Check GatewayPorts
if grep -q "^GatewayPorts clientspecified" "$SSHD_CONFIG" 2>/dev/null; then
    success "GatewayPorts already configured"
else
    echo "SSH reverse tunnels require 'GatewayPorts clientspecified' in sshd_config."
    echo "This allows tunneled services to be accessible from outside localhost."
    echo ""
    if ask_yn "Add 'GatewayPorts clientspecified' to $SSHD_CONFIG?"; then
        echo 'GatewayPorts clientspecified' | sudo tee -a "$SSHD_CONFIG" > /dev/null
        success "Added to $SSHD_CONFIG"

        if [[ "$OS_TYPE" == "linux" ]]; then
            sudo systemctl restart sshd 2>/dev/null || sudo systemctl restart ssh 2>/dev/null
            success "sshd restarted"
        elif [[ "$OS_TYPE" == "macos" ]]; then
            sudo launchctl stop com.openssh.sshd 2>/dev/null
            sudo launchctl start com.openssh.sshd 2>/dev/null
            success "sshd restarted"
        fi
    else
        warn "Skipping. Tunnels may only be accessible on localhost without GatewayPorts."
    fi
fi

# ============================================================================
header "Step 5/7: Reverse Proxy Setup"
# ============================================================================

echo "tunnelctl generates reverse proxy configuration so HTTP services"
echo "are accessible via subdomains (e.g. nas.yourdomain.com)."
echo ""
echo "Choose a reverse proxy:"
echo "  1) NGINX  - widely used, needs certbot for TLS"
echo "  2) Caddy  - automatic TLS via Let's Encrypt"
echo "  3) None   - skip reverse proxy (direct port access only)"
echo ""

PROXY_CHOICE=$(ask "Choice" "1")

case "$PROXY_CHOICE" in
    1)
        PROXY_TYPE="nginx"
        if command -v nginx &>/dev/null; then
            success "NGINX found: $(nginx -v 2>&1)"
        else
            if [[ "$OS_TYPE" == "linux" ]] && ask_yn "Install NGINX?"; then
                sudo apt-get update -qq && sudo apt-get install -y -qq nginx
                success "NGINX installed"
            elif [[ "$OS_TYPE" == "macos" ]] && ask_yn "Install NGINX via Homebrew?"; then
                brew install nginx
                success "NGINX installed"
            else
                warn "NGINX not installed. Install it before running the endpoint service."
            fi
        fi

        # Check for stream module support
        if command -v nginx &>/dev/null; then
            NGINX_CONF=$(nginx -t 2>&1 | grep -oP 'configuration file \K\S+' || echo "/etc/nginx/nginx.conf")
            if ! grep -q "^stream" "$NGINX_CONF" 2>/dev/null; then
                echo ""
                warn "NGINX stream{} block not found in $NGINX_CONF"
                echo "  TCP tunnels (SSH, databases) require the stream module."
                echo "  Add this to the end of $NGINX_CONF:"
                echo ""
                echo "    stream {"
                echo "        include /etc/nginx/conf.d/*.stream.conf;"
                echo "    }"
                echo ""
            fi
        fi
        ;;
    2)
        PROXY_TYPE="caddy"
        if command -v caddy &>/dev/null; then
            success "Caddy found: $(caddy version 2>&1)"
        else
            if [[ "$OS_TYPE" == "linux" ]] && ask_yn "Install Caddy?"; then
                sudo apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
                curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
                curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
                sudo apt-get update -qq && sudo apt-get install -y -qq caddy
                success "Caddy installed"
            else
                warn "Caddy not installed."
            fi
        fi
        ;;
    3)
        PROXY_TYPE="none"
        info "Skipping reverse proxy setup. Services accessible via direct port."
        ;;
esac

# ============================================================================
header "Step 6/7: Endpoint Configuration"
# ============================================================================

EP_NAME=$(ask "Name for this endpoint (must match agent config)" "$(hostname -s)")
HTTP_DOMAIN=$(ask "Wildcard domain for HTTP tunnels (e.g. *.home.example.com)" "")

CONFIG_DIR="/etc/${PROXY_TYPE:-nginx}/conf.d"
if [[ "$PROXY_TYPE" == "none" ]]; then
    CONFIG_DIR="/tmp"
fi

cat > "$CONFIG_PATH" << EOF
global:
  reconnect_interval: 30
  health_check_interval: 30
  health_check_timeout: 10
  log_level: INFO
  state_db: ./tunnelctl-endpoint.db
  api_port: 8081
  api_host: 127.0.0.1

telegram:
  enabled: false

endpoints:
  - name: $EP_NAME
    host: 0.0.0.0
    port: 22
    user: $TUNNEL_USER
    proxy:
      type: ${PROXY_TYPE:-nginx}
      http_domain: "$HTTP_DOMAIN"
      ssl: true
      config_path: $CONFIG_DIR/tunnelctl.conf
      reload_command: "${PROXY_TYPE:-echo} -s reload"

# Define the same tunnels as your agent config so the endpoint
# knows which ports to monitor and proxy.
tunnels: []
EOF

success "Endpoint configuration written to $CONFIG_PATH"
echo ""
echo "  Important: Copy the 'tunnels' section from your agent's config.yaml"
echo "  into this file so the endpoint knows which ports to monitor."

# ============================================================================
header "Step 7/7: Firewall & Service Installation"
# ============================================================================

# Firewall
if command -v ufw &>/dev/null; then
    echo "Detected UFW firewall."
    if ask_yn "Configure firewall rules for tunnelctl?"; then
        sudo ufw allow 22/tcp comment "SSH"
        sudo ufw allow 80/tcp comment "HTTP"
        sudo ufw allow 443/tcp comment "HTTPS"

        PORT_RANGE=$(ask "Tunnel port range to open (e.g. 2200:2299)" "2200:9099")
        sudo ufw allow "$PORT_RANGE/tcp" comment "tunnelctl tunnels"

        success "Firewall rules added"
        sudo ufw status numbered
    fi
elif command -v firewall-cmd &>/dev/null; then
    echo "Detected firewalld."
    if ask_yn "Configure firewall rules for tunnelctl?"; then
        sudo firewall-cmd --permanent --add-service=ssh
        sudo firewall-cmd --permanent --add-service=http
        sudo firewall-cmd --permanent --add-service=https

        PORT_RANGE=$(ask "Tunnel port range (e.g. 2200-9099)" "2200-9099")
        sudo firewall-cmd --permanent --add-port="$PORT_RANGE/tcp"
        sudo firewall-cmd --reload

        success "Firewall rules added"
    fi
fi

# Service installation
echo ""
if ask_yn "Install tunnelctl endpoint as a system service?"; then
    TUNNELCTL_BIN=$(which tunnelctl 2>/dev/null || echo "$(pwd)/.venv/bin/tunnelctl")
    WORK_DIR=$(pwd)

    if [[ "$OS_TYPE" == "linux" ]]; then
        sudo tee /etc/systemd/system/tunnelctl-endpoint.service > /dev/null << EOF
[Unit]
Description=tunnelctl endpoint service
After=network-online.target sshd.service
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$WORK_DIR
ExecStart=$TUNNELCTL_BIN endpoint -c $WORK_DIR/$CONFIG_PATH
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

        sudo systemctl daemon-reload
        sudo systemctl enable tunnelctl-endpoint
        success "Systemd service installed: tunnelctl-endpoint"

        if ask_yn "Start the endpoint service now?"; then
            sudo systemctl start tunnelctl-endpoint
            sleep 2
            if systemctl is-active --quiet tunnelctl-endpoint; then
                success "Endpoint service is running"
            else
                warn "Check: sudo journalctl -u tunnelctl-endpoint -f"
            fi
        fi

    elif [[ "$OS_TYPE" == "macos" ]]; then
        PLIST_PATH="$HOME/Library/LaunchAgents/com.tunnelctl.endpoint.plist"
        mkdir -p "$HOME/Library/LaunchAgents"

        cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.tunnelctl.endpoint</string>
    <key>ProgramArguments</key>
    <array>
        <string>$TUNNELCTL_BIN</string>
        <string>endpoint</string>
        <string>-c</string>
        <string>$WORK_DIR/$CONFIG_PATH</string>
    </array>
    <key>WorkingDirectory</key><string>$WORK_DIR</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/tmp/tunnelctl-endpoint.log</string>
    <key>StandardErrorPath</key><string>/tmp/tunnelctl-endpoint.log</string>
</dict>
</plist>
EOF

        success "launchd plist written to $PLIST_PATH"
        if ask_yn "Start the endpoint service now?"; then
            launchctl load "$PLIST_PATH" 2>/dev/null || true
            success "Endpoint service started"
        fi
    fi
fi

# ============================================================================
echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║       Endpoint Setup Complete!               ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo "  Config:       $CONFIG_PATH"
echo "  Tunnel user:  $TUNNEL_USER"
echo "  Proxy type:   ${PROXY_TYPE:-none}"
echo ""
echo "  Next steps:"
echo "    1. Copy tunnel definitions from your agent config into $CONFIG_PATH"
echo "    2. If using DNS subdomains, create a wildcard A record:"
echo "       $HTTP_DOMAIN  ->  $(curl -s ifconfig.me 2>/dev/null || echo '<this-server-ip>')"
echo "    3. Start the agent on the Starlink side"
echo "    4. Verify: tunnelctl status (from the agent machine)"
echo ""
