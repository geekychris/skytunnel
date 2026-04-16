#!/usr/bin/env bash
set -euo pipefail

CONFIG="${1:-config.yaml}"

echo "=== tunnelctl Connectivity Check ==="

if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

# Parse endpoints from YAML using Python
python3 -c "
import yaml, sys, os

with open('$CONFIG') as f:
    cfg = yaml.safe_load(f)

for ep in cfg.get('endpoints', []):
    name = ep['name']
    host = ep['host']
    port = ep.get('port', 22)
    user = ep.get('user', 'tunnel')
    key_file = ep.get('key_file', '~/.ssh/tunnel_key').replace('~', os.path.expanduser('~'))
    print(f'{name}|{host}|{port}|{user}|{key_file}')
" | while IFS='|' read -r name host port user key_file; do
    echo -n "Checking $name ($user@$host:$port)... "

    if ssh -i "$key_file" -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
       -o BatchMode=yes "$user@$host" -p "$port" "echo ok" 2>/dev/null; then
        echo "OK"
    else
        echo "FAILED"
    fi
done

echo ""
echo "Done."
