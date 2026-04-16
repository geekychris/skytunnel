#!/usr/bin/env bash
set -euo pipefail

KEY_NAME="${1:-tunnel_key}"
KEY_PATH="$HOME/.ssh/$KEY_NAME"

echo "=== tunnelctl SSH Key Setup ==="

if [[ -f "$KEY_PATH" ]]; then
    echo "Key already exists at $KEY_PATH"
    echo "To regenerate, remove it first: rm $KEY_PATH $KEY_PATH.pub"
    exit 0
fi

echo "Generating SSH key pair..."
ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -C "tunnelctl"
chmod 600 "$KEY_PATH"

echo ""
echo "Key generated:"
echo "  Private: $KEY_PATH"
echo "  Public:  $KEY_PATH.pub"
echo ""
echo "Next steps:"
echo "  1. Copy the public key to each endpoint server:"
echo "     ssh-copy-id -i $KEY_PATH.pub tunnel@<endpoint-host>"
echo ""
echo "  2. On each endpoint, ensure the tunnel user exists:"
echo "     sudo useradd -m -s /bin/bash tunnel"
echo ""
echo "  3. On each endpoint, allow GatewayPorts in sshd_config:"
echo "     echo 'GatewayPorts clientspecified' | sudo tee -a /etc/ssh/sshd_config"
echo "     sudo systemctl restart sshd"
echo ""
echo "Public key contents:"
cat "$KEY_PATH.pub"
