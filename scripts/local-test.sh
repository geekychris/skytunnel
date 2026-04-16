#!/usr/bin/env bash
set -euo pipefail

echo "=== tunnelctl Local Test Setup ==="
echo ""
echo "This script sets up everything needed to test tunnelctl on a single machine."
echo "It uses localhost SSH and a simple Python HTTP server as the 'internal device'."
echo ""

# --- 1. Check prerequisites ---
echo "[1/5] Checking prerequisites..."

if ! ssh -o BatchMode=yes -o ConnectTimeout=2 localhost true 2>/dev/null; then
    echo ""
    echo "ERROR: Cannot SSH to localhost."
    echo ""
    echo "Fix: Enable Remote Login in System Preferences > General > Sharing > Remote Login"
    echo "  (or on Linux: sudo systemctl start sshd)"
    echo ""
    echo "Then add your key to authorized_keys:"
    echo "  cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys"
    echo "  chmod 600 ~/.ssh/authorized_keys"
    echo ""
    exit 1
fi
echo "  SSH to localhost: OK"

# --- 2. Generate test SSH key ---
echo "[2/5] Setting up SSH key..."
KEY_PATH="$HOME/.ssh/tunnelctl_test_key"
if [[ ! -f "$KEY_PATH" ]]; then
    ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -C "tunnelctl-test" -q
    cat "$KEY_PATH.pub" >> ~/.ssh/authorized_keys
    echo "  Generated $KEY_PATH and added to authorized_keys"
else
    echo "  Key already exists at $KEY_PATH"
fi

# Verify key works
if ! ssh -i "$KEY_PATH" -o BatchMode=yes -o ConnectTimeout=2 localhost true 2>/dev/null; then
    echo "  Adding key to authorized_keys..."
    cat "$KEY_PATH.pub" >> ~/.ssh/authorized_keys
fi

# --- 3. Write test config ---
echo "[3/5] Writing test config..."
CONFIG_PATH="config.local-test.yaml"
cat > "$CONFIG_PATH" << 'YAML'
global:
  reconnect_interval: 10
  health_check_interval: 15
  health_check_timeout: 5
  log_level: DEBUG
  state_db: ":memory:"
  api_port: 8080
  api_host: 127.0.0.1

telegram:
  enabled: false

endpoints:
  - name: local-endpoint
    host: 127.0.0.1
    port: 22
    user: CURRENT_USER
    key_file: KEY_FILE_PATH
    proxy:
      type: nginx
      http_domain: "*.localhost"
      ssl: false
      config_path: /tmp/tunnelctl-test-nginx.conf
      reload_command: "echo nginx-reload-simulated"

tunnels:
  - name: test-http
    internal_host: 127.0.0.1
    internal_port: 9999
    remote_port: 9998
    protocol: http
    endpoints: [local-endpoint]
    subdomain: test

  - name: test-tcp
    internal_host: 127.0.0.1
    internal_port: 9999
    remote_port: 9997
    protocol: tcp
    endpoints: [local-endpoint]

  - name: test-ssh
    internal_host: 127.0.0.1
    internal_port: 22
    remote_port: 9996
    protocol: tcp
    endpoints: [local-endpoint]
YAML

# Replace placeholders
sed -i.bak "s|CURRENT_USER|$(whoami)|g" "$CONFIG_PATH"
sed -i.bak "s|KEY_FILE_PATH|$KEY_PATH|g" "$CONFIG_PATH"
rm -f "${CONFIG_PATH}.bak"

echo "  Wrote $CONFIG_PATH"

# --- 4. Start a mock internal service ---
echo "[4/5] Starting mock internal HTTP server on port 9999..."
python3 -c "
import http.server, threading, time

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Hello from the internal device! tunnelctl works!')
    def log_message(self, *args):
        pass

server = http.server.HTTPServer(('127.0.0.1', 9999), Handler)
print(f'  Mock server running on http://127.0.0.1:9999')
server.serve_forever()
" &
MOCK_PID=$!

# Wait for it to be ready
sleep 1

# --- 5. Instructions ---
echo "[5/5] Ready!"
echo ""
echo "============================================"
echo "  Local Test Environment Ready"
echo "============================================"
echo ""
echo "Mock HTTP server: http://127.0.0.1:9999  (PID: $MOCK_PID)"
echo "Config file:      $CONFIG_PATH"
echo ""
echo "Now open another terminal and run:"
echo ""
echo "  tunnelctl agent -c $CONFIG_PATH"
echo ""
echo "Then test with:"
echo ""
echo "  # Check the web dashboard"
echo "  open http://127.0.0.1:8080"
echo ""
echo "  # Check tunnel status via CLI"
echo "  tunnelctl status"
echo ""
echo "  # Test the HTTP tunnel (port 9998 -> 9999)"
echo "  curl http://127.0.0.1:9998"
echo ""
echo "  # Test the TCP tunnel (port 9997 -> 9999)"
echo "  curl http://127.0.0.1:9997"
echo ""
echo "  # SSH through the tunnel (port 9996 -> 22)"
echo "  ssh -p 9996 $(whoami)@127.0.0.1"
echo ""
echo "  # Add a tunnel dynamically"
echo "  tunnelctl tunnels add --name demo --host 127.0.0.1 --port 9999 --remote-port 9995"
echo ""
echo "  # View logs"
echo "  tunnelctl logs"
echo ""
echo "Press Ctrl+C to stop the mock server."
echo ""

# Keep mock server running until Ctrl+C
trap "kill $MOCK_PID 2>/dev/null; echo 'Stopped.'; exit 0" INT TERM
wait $MOCK_PID
